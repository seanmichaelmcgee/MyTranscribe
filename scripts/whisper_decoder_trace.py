"""Bounded public-call metadata for experimental replay; no model/package imports."""
import hashlib
import json
import math
from numbers import Integral

MAX_CALLS = 256
MAX_SEGMENTS = 4096
MAX_TOKENS = 4096
MAX_PROMPT_TEXT = 8192
OPTION_FIELDS = ("beam_size", "best_of", "patience", "length_penalty", "repetition_penalty",
    "no_repeat_ngram_size", "log_prob_threshold", "no_speech_threshold", "compression_ratio_threshold",
    "condition_on_previous_text", "prompt_reset_on_temperature", "without_timestamps", "max_new_tokens",
    "suppress_blank", "word_timestamps", "max_initial_timestamp", "hallucination_silence_threshold")
VAD_FIELDS = ("threshold", "neg_threshold", "min_speech_duration_ms", "max_speech_duration_s",
    "min_silence_duration_ms", "speech_pad_ms", "min_silence_at_max_speech", "use_max_poss_sil_at_max_speech")
UNOBSERVED = ["native_prompt_tokens", "native_generation_attempts", "selected_fallback_attempt",
    "fallback_rejection_reason", "native_stop_reason", "vad_window_to_original_audio_mapping",
    "warmup_clip_repeat_chunk_binding", "context_builder_calls", "topic_rotation", "recording_resets"]


def numeric_fields(value, names):
    result = {}
    for name in names:
        item = value.get(name) if isinstance(value, dict) else getattr(value, name, None)
        if type(item) in (int, float, bool):
            result[name] = item if type(item) is not float or math.isfinite(item) else None
    return result


class DecoderTrace:
    def __init__(self, prompt_text=False):
        self.prompt_text = prompt_text
        self.calls, self.failures = [], []
        self.segment_count = 0

    def fail(self, stage, error):
        if len(self.failures) < 16:
            self.failures.append(dict(stage=stage, exception_class=type(error).__name__))

    def safe(self, stage, callback):
        try:
            return callback()
        except Exception as error:
            self.fail(stage, error)
            return None

    def begin(self, audio, kwargs, temperatures):
        if len(self.calls) >= MAX_CALLS:
            self.fail("call_limit", OverflowError())
            return None
        call = dict(call_index=len(self.calls), completed=False, state="started", segments=[],
                    finish_reason=None, finish_reason_availability="not_observed_at_public_call_boundary")
        self.calls.append(call)

        def capture():
            if audio.ndim != 1 or audio.dtype.kind != "f":
                raise TypeError("Expected existing mono float PCM")
            call["pre_vad_audio"] = dict(sha256=hashlib.sha256(audio.tobytes(order="C")).hexdigest(),
                frames=len(audio), sample_rate=16000, dtype=audio.dtype.str,
                hash_representation="actual input floating PCM in C order; no cast or rescale")
            prompt = kwargs.get("initial_prompt")
            if prompt is not None and not isinstance(prompt, str):
                raise TypeError("Nontext initial prompt is not observed by this layer")
            call["initial_prompt"] = dict(passed="initial_prompt" in kwargs,
                sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt is not None else None,
                char_count=len(prompt) if prompt is not None else 0,
                token_count=None, token_count_method="unobserved; tokenizer is not called for tracing")
            if self.prompt_text:
                if prompt is not None and len(prompt) > MAX_PROMPT_TEXT:
                    raise OverflowError("Prompt text trace limit")
                call["initial_prompt"]["text"] = prompt
            call["passed_max_new_tokens"] = kwargs.get("max_new_tokens") if type(kwargs.get("max_new_tokens")) is int else None
            call["max_new_tokens_passed"] = "max_new_tokens" in kwargs
            call["passed_numeric_boolean_options"] = numeric_fields(kwargs, OPTION_FIELDS + ("vad_filter",))
            schedule = temperatures if isinstance(temperatures, (tuple, list)) else [temperatures]
            if len(schedule) > 16 or any(type(t) not in (int, float) or not math.isfinite(t) for t in schedule):
                raise TypeError("Unsupported configured temperature schedule")
            call["configured_temperature_schedule"] = list(schedule)
            call["schedule_provenance"] = "actual passed temperature if present, otherwise inspected original default; not observed attempts"
        self.safe("call_metadata", capture)
        return call

    def info(self, call, info):
        if call is None:
            return
        def capture():
            call["info_numeric_boolean"] = numeric_fields(info, ("duration", "duration_after_vad", "language_probability"))
            call["transcription_options_numeric_boolean"] = numeric_fields(getattr(info, "transcription_options", None), OPTION_FIELDS)
            call["vad_options_numeric_boolean"] = numeric_fields(getattr(info, "vad_options", None), VAD_FIELDS)
        self.safe("info_metadata", capture)

    def segment(self, call, segment):
        if call is None:
            return
        if self.segment_count >= MAX_SEGMENTS:
            self.fail("segment_limit", OverflowError())
            return
        self.segment_count += 1
        item = dict(finish_reason=None, finish_reason_availability="not_exposed_in_inspected_public_segment",
                    token_count=None, token_sha256=None)
        call["segments"].append(item)
        def capture():
            item.update(numeric_fields(segment, ("id", "seek", "start", "end", "temperature", "avg_logprob",
                                                 "compression_ratio", "no_speech_prob")))
            tokens = getattr(segment, "tokens", None)
            if tokens is None:
                return
            if not isinstance(tokens, (list, tuple)):
                raise TypeError("Token telemetry requires an existing list; never consume an iterator")
            item["token_count"] = len(tokens)
            if len(tokens) > MAX_TOKENS:
                raise OverflowError("Segment token hash limit")
            if any(not isinstance(token, Integral) or isinstance(token, bool) for token in tokens):
                raise TypeError("Token list must contain integers")
            encoded = json.dumps([int(token) for token in tokens], separators=(",", ":")).encode("ascii")
            item["token_sha256"] = hashlib.sha256(encoded).hexdigest()
            item["token_hash_representation"] = "compact JSON integer list; IDs not retained"
        self.safe("segment_metadata", capture)

    def end(self, call, state, error=None):
        if call is not None:
            call.update(state=state, completed=state == "exhausted")
            if error is not None:
                call["recognition_exception_class"] = type(error).__name__

    def snapshot(self):
        return dict(schema="whisper-public-decoder-trace-v1", enabled=True, prompt_text_enabled=self.prompt_text,
            complete=bool(self.calls) and not self.failures and all(call["completed"] for call in self.calls),
            limits=dict(calls=MAX_CALLS, segments=MAX_SEGMENTS, token_hash_length=MAX_TOKENS, prompt_text_chars=MAX_PROMPT_TEXT),
            failures=list(self.failures), calls=self.calls, unobserved=list(UNOBSERVED),
            reported_temperature_is_selected_attempt_identity=False, stopping_reason_observed=False,
            token_counts_are_emitted_segments_not_native_generation_totals=True)
