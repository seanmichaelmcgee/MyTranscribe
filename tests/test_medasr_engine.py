"""Numerical failure guard without importing Torch or loading a model."""
from types import SimpleNamespace

import numpy as np
import pytest

from medasr_engine import checked_ctc_sequences


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf])
def test_nonfinite_logits_cannot_be_silently_decoded_as_blanks(bad):
    output = SimpleNamespace(logits=np.array([[0.0, bad]]), sequences=np.array([[0]]))
    with pytest.raises(RuntimeError, match='nonfinite logits'):
        checked_ctc_sequences(output, np.isfinite)


def test_finite_logits_preserve_generated_sequences():
    output = SimpleNamespace(logits=np.array([[1.0, -2.0]]), sequences=np.array([[1]]))
    assert checked_ctc_sequences(output, np.isfinite) is output.sequences
