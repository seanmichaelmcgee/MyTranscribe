"""Optional instance-owned native attempt observations; no inference imports.

Only existing lists are hashed. Native objects/IDs and token text are never saved.
The installed faster-whisper fallback can return an earlier result together with
the last attempted temperature, so these identities are observed separately.
"""
from contextlib import contextmanager
import hashlib
import inspect
import json
import math
from numbers import Integral
from pathlib import Path
import threading

from whisper_decoder_trace import DecoderTrace, numeric_fields, OPTION_FIELDS, MAX_TOKENS

MAX_WINDOWS = 256
MAX_PROMPTS = 512
MAX_ATTEMPTS = 1536
MAX_RESULTS = 16
GENERATE_FIELDS = ("beam_size", "patience", "num_hypotheses", "sampling_topk",
    "sampling_temperature", "length_penalty", "repetition_penalty", "no_repeat_ngram_size",
    "max_length", "return_scores", "return_no_speech_prob", "suppress_blank",
    "max_initial_timestamp_index")


def token_metadata(tokens):
    if not isinstance(tokens, (list, tuple)):
        raise TypeError("Never consume token iterators")
    if len(tokens) > MAX_TOKENS:
        raise OverflowError("Token hash limit")
    if any(not isinstance(t, Integral) or isinstance(t, bool) for t in tokens):
        raise TypeError("Expected integer tokens")
    encoded = json.dumps([int(t) for t in tokens], separators=(",", ":")).encode("ascii")
    return dict(count=len(tokens), sha256=hashlib.sha256(encoded).hexdigest(),
                representation="compact JSON integer list; IDs not retained")


class NativeTraceRecorder(DecoderTrace):
    def __init__(self):
        super().__init__()
        self.windows, self.prompts, self.attempts, self.implementations = [], [], [], []

    def snapshot(self, public_complete=None):
        def bound_window(window):
            prompt_index = window.get("prompt_index")
            return (window.get("public_call_index") is not None and
                type(prompt_index) is int and 0 <= prompt_index < len(self.prompts) and
                self.prompts[prompt_index]["public_call_index"] == window["public_call_index"] and
                self.prompts[prompt_index]["native_prompt"] == window["native_prompt"])
        return dict(schema="whisper-native-attempt-trace-v1", enabled=True,
            complete=bool(self.windows) and not self.failures and public_complete is not False and
                     all(w.get("state") == "returned" and w.get("selected_attempt_index") is not None and
                         bound_window(w) for w in self.windows) and
                     all(a.get("state") == "returned" and a.get("results") and
                         type(a.get("window_index")) is int and 0 <= a["window_index"] < len(self.windows)
                         for a in self.attempts),
            public_layer_complete=public_complete,
            completeness_scope="observed Python fallback windows/native attempts only",
            limits=dict(windows=MAX_WINDOWS, prompts=MAX_PROMPTS, attempts=MAX_ATTEMPTS,
                        results_per_attempt=MAX_RESULTS, token_hash_length=MAX_TOKENS),
            failures=list(self.failures), implementations=self.implementations,
            windows=self.windows, prompts=self.prompts,
            attempts=self.attempts, stopping_reason_observed=False,
            unobserved=["fallback_rejection_cause", "native_stop_reason",
                "vad_window_to_original_audio_mapping", "warmup_clip_repeat_chunk_binding",
                "context_builder_calls", "topic_rotation", "recording_resets"])


class GenerateFacade:
    """Forward native attributes and calls; intercept only generate on this owner."""
    def __init__(self, target, owner):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_owner", owner)

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __setattr__(self, name, value):
        setattr(self._target, name, value)

    def generate(self, *args, **kwargs):
        return self._owner.generate(self._target.generate, args, kwargs)


class NativeAttemptTrace:
    def __init__(self, model, recorder):
        self.model, self.recorder = model, recorder
        self.local = threading.local()
        self.saved = []

    def __enter__(self):
        if "_trial_native_trace_owner" in vars(self.model):
            error = ValueError("Simultaneous native trace owners are not supported")
            self.recorder.fail("native_owner_conflict", error)
            raise error
        try:
            self.saved.append(("_trial_native_trace_owner", False, None))
            self.model._trial_native_trace_owner = self
            original_prompt = self.model.get_prompt
            original_fallback = self.model.generate_with_fallback
            prompt_signature = inspect.signature(original_prompt)
            fallback_signature = inspect.signature(original_fallback)
            def implementation():
                for method in (original_prompt, original_fallback):
                    path = inspect.getsourcefile(method)
                    self.recorder.implementations.append(dict(module=method.__module__,
                        qualname=method.__qualname__, source_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()))
            self.recorder.safe("implementation_identity", implementation)
            # The outer runtime adapter also replaces transcribe after installation.
            # Include that instance binding in the owner's final restoration.
            if hasattr(self.model, "transcribe"):
                own = vars(self.model)
                self.saved.append(("transcribe", "transcribe" in own, own.get("transcribe")))

            def get_prompt(*args, **kwargs):
                result = original_prompt(*args, **kwargs)
                self.local.pending_prompt = None
                def observe():
                    if len(self.recorder.prompts) >= MAX_PROMPTS:
                        raise OverflowError("Prompt limit")
                    bound = prompt_signature.bind(*args, **kwargs).arguments
                    item = dict(prompt_index=len(self.recorder.prompts),
                        public_call_index=getattr(self.local, "call", None),
                        native_prompt=token_metadata(result),
                        previous_tokens=token_metadata(bound["previous_tokens"]),
                        without_timestamps=bound.get("without_timestamps", False)
                            if type(bound.get("without_timestamps", False)) is bool else None,
                        prefix_present=bound.get("prefix") is not None,
                        hotwords_present=bound.get("hotwords") is not None)
                    self.recorder.prompts.append(item)
                    self.local.pending_prompt = (result, item["prompt_index"])
                self.recorder.safe("get_prompt_metadata", observe)
                return result

            def fallback(*args, **kwargs):
                previous = getattr(self.local, "window", None)
                window = None
                matches = []
                def begin():
                    nonlocal window
                    if len(self.recorder.windows) >= MAX_WINDOWS:
                        raise OverflowError("Window limit")
                    bound = fallback_signature.bind(*args, **kwargs).arguments
                    pending = getattr(self.local, "pending_prompt", None)
                    window = dict(window_index=len(self.recorder.windows),
                        public_call_index=getattr(self.local, "call", None), state="started",
                        native_prompt=token_metadata(bound["prompt"]),
                        prompt_index=pending[1] if pending and pending[0] is bound["prompt"] else None,
                        options_numeric_boolean=numeric_fields(bound["options"], OPTION_FIELDS),
                        selected_attempt_index=None, selected_result_index=None,
                        selected_attempt_temperature=None, reported_final_temperature=None,
                        internal_reset_event_observed=False,
                        rejection_cause=None, finish_reason=None,
                        finish_reason_availability="not_exposed_in_inspected_installed_result")
                    self.recorder.windows.append(window)
                self.recorder.safe("fallback_begin", begin)
                self.local.pending_prompt = None
                self.local.window = (window, matches)
                try:
                    result = original_fallback(*args, **kwargs)
                    def finish():
                        if window is None:
                            return
                        window.update(state="returned", **numeric_fields(
                            dict(reported_final_temperature=result[2], avg_logprob=result[1],
                                 compression_ratio=result[3]),
                            ("reported_final_temperature", "avg_logprob", "compression_ratio")))
                        candidates = [m for m in matches if m[0] is result[0]]
                        if len(candidates) != 1:
                            raise LookupError("Selected result identity absent or ambiguous")
                        selected = candidates[0]
                        window.update(selected_attempt_index=selected[1], selected_result_index=selected[2],
                                      selected_attempt_temperature=selected[3])
                    self.recorder.safe("fallback_selected_result", finish)
                    return result
                except BaseException as error:
                    self.recorder.safe("fallback_error", lambda: window.update(
                        state="recognition_error", recognition_exception_class=type(error).__name__)
                        if window is not None else None)
                    raise
                finally:
                    self.local.window = previous
                    matches.clear()

            for name, value in (("model", GenerateFacade(self.model.model, self)),
                                ("get_prompt", get_prompt), ("generate_with_fallback", fallback)):
                own = vars(self.model)
                self.saved.append((name, name in own, own.get(name)))
                setattr(self.model, name, value)
        except Exception as error:
            self.__exit__(None, None, None)
            self.recorder.fail("native_install", error)
        return self

    def __exit__(self, *_):
        for name, had_own, value in reversed(self.saved):
            def restore():
                if had_own:
                    setattr(self.model, name, value)
                elif name in vars(self.model):
                    delattr(self.model, name)
            # Attempt every restoration even if an instance refuses one binding.
            # A telemetry cleanup error must not mask a recognition exception.
            self.recorder.safe("restore_" + name, restore)
        self.saved.clear()

    @contextmanager
    def in_call(self, index):
        old = getattr(self.local, "call", None)
        self.local.call = index
        try:
            yield
        finally:
            self.local.call = old

    def iter_in_call(self, segments, index):
        # No prefetch or close/send/throw forwarding: retain the old tracked loop.
        iterator = iter(segments)
        while True:
            with self.in_call(index):
                try:
                    segment = next(iterator)
                except StopIteration:
                    return
            yield segment

    def generate(self, original, args, kwargs):
        context = getattr(self.local, "window", None)
        attempt = None
        def begin():
            nonlocal attempt
            if len(self.recorder.attempts) >= MAX_ATTEMPTS:
                raise OverflowError("Attempt limit")
            prompts = args[1] if len(args) > 1 else kwargs["prompts"]
            if not isinstance(prompts, (list, tuple)) or len(prompts) > MAX_RESULTS:
                raise TypeError("Expected bounded existing native prompt batch")
            fields = numeric_fields(kwargs, GENERATE_FIELDS)
            temperature = fields.get("sampling_temperature")
            provenance = "actual sampling_temperature kwarg"
            if temperature is None:
                if context and "beam_size" in fields and "patience" in fields:
                    temperature = 0.0
                    provenance = "observed beam branch in inspected generate_with_fallback"
                else:
                    provenance = "unobserved"
            attempt = dict(attempt_index=len(self.recorder.attempts),
                window_index=context[0]["window_index"] if context and context[0] else None,
                public_call_index=getattr(self.local, "call", None), state="started",
                native_prompts=[token_metadata(p) for p in prompts], numeric_boolean_kwargs=fields,
                suppress_tokens=token_metadata(kwargs["suppress_tokens"]) if "suppress_tokens" in kwargs else None,
                attempt_temperature=temperature, temperature_provenance=provenance, results=[],
                finish_reason=None, rejection_cause=None)
            self.recorder.attempts.append(attempt)
        self.recorder.safe("generate_begin", begin)
        try:
            result = original(*args, **kwargs)
        except BaseException as error:
            self.recorder.safe("generate_error", lambda: attempt.update(state="recognition_error",
                recognition_exception_class=type(error).__name__) if attempt is not None else None)
            raise
        def finish():
            if attempt is None:
                return
            attempt["state"] = "returned"
            if not isinstance(result, (list, tuple)):
                raise TypeError("Never consume native result iterators")
            if len(result) > MAX_RESULTS:
                raise OverflowError("Native result limit")
            for index, item in enumerate(result):
                if context and context[0] is not None:
                    context[1].append((item, attempt["attempt_index"], index, attempt["attempt_temperature"]))
                sequences = item.sequences_ids
                if not isinstance(sequences, (list, tuple)) or len(sequences) > MAX_RESULTS:
                    raise TypeError("Expected bounded existing generated sequences")
                observed = dict(result_index=index,
                    generated_sequences=[token_metadata(s) for s in sequences], finish_reason=None,
                    **numeric_fields(item, ("no_speech_prob",)))
                attempt["results"].append(observed)
                scores = getattr(item, "scores", None)
                if scores is not None:
                    if not isinstance(scores, (list, tuple)) or len(scores) > MAX_RESULTS:
                        raise TypeError("Expected bounded existing scores")
                    if any(type(score) not in (float, int) or not math.isfinite(score) for score in scores):
                        raise TypeError("Expected finite numeric scores")
                    observed["scores"] = list(scores)
        self.recorder.safe("generate_result", finish)
        return result
