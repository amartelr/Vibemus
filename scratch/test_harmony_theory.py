"""Fase 1 del plan de mejoras: clasificación de acordes, extracción, grados romanos, progresiones y estilo.
Uso: .venv/bin/python -m pytest scratch/test_harmony_theory.py"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.web.harmony import (clean_and_extract_chords, get_roman_numeral, infer_emotional_style,  # noqa: E402
                             infer_progression, infer_progression_full, parse_chord_root_and_quality, style_scores)


# ── 1. Cualidad del acorde ────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("chord,quality", [
    ("Bdim", "dim"), ("B°", "dim"), ("Bo", "dim"), ("Bdim7", "dim"), ("Bø", "dim"),
    ("Baug", "aug"), ("B+", "aug"),
    ("Bm", "minor"), ("Bmin", "minor"), ("Bm7", "minor"), ("Bm7b5", "minor"), ("Bmadd9", "minor"),
    ("Bmaj7", "major"), ("BM7", "major"), ("B7", "major"), ("B", "major"), ("Bsus4", "major"), ("Badd9", "major"),
    ("F#m/C#", "minor"), ("Bb", "major"),
])
def test_chord_quality(chord, quality):
    assert parse_chord_root_and_quality(chord)[1] == quality


# ── 2. Extracción ────────────────────────────────────────────────────────────────────────────────────────────
def test_chord_only_line_keeps_single_letters():
    assert clean_and_extract_chords("<song> A Amaj7 A D F#m D/F# G") == ["A", "Amaj7", "A", "D", "F#m", "D/F#", "G"]


def test_lyrics_do_not_produce_chords():
    assert clean_and_extract_chords("A man walked into a bar and ordered a drink") == []


def test_isolated_A_in_a_sentence_is_not_a_chord():
    text = "Am F C G\nI walked down A road that I knew\nAm F C G"
    assert clean_and_extract_chords(text) == ["Am", "F", "C", "G", "Am", "F", "C", "G"]


def test_tagged_chords_take_priority():
    text = "[Verse 1]\n[ch]Am[/ch] A song for [ch]F[/ch] you and [ch]C[/ch] me [ch]G[/ch] now"
    assert clean_and_extract_chords(text) == ["Am", "F", "C", "G"]


def test_free_text_chord_line_between_lyrics():
    text = "Hello A friend\n  C        G\nHello again"
    assert clean_and_extract_chords(text) == ["C", "G"]


# ── 3. Grados romanos en menor ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("chord,roman", [
    ("Am", "i"), ("Bdim", "ii°"), ("C", "III"), ("C#", "#III"), ("Dm", "iv"), ("D", "IV"), ("Em", "v"), ("E", "V"),
    ("F", "VI"), ("F#", "#VI"), ("F#dim", "vi°"), ("G", "VII"), ("G#", "#VII"), ("G#dim", "vii°"),
])
def test_roman_numerals_a_minor(chord, roman):
    assert get_roman_numeral("A", "Minor", chord) == roman


@pytest.mark.parametrize("chord,roman", [
    ("C", "I"), ("Dm", "ii"), ("Em", "iii"), ("F", "IV"), ("G", "V"), ("Am", "vi"), ("Bdim", "vii°"),
    ("Bb", "bVII"), ("Eb", "bIII"), ("Ab", "bVI"),
])
def test_roman_numerals_c_major(chord, roman):
    assert get_roman_numeral("C", "Major", chord) == roman


# ── 4. Progresión y estilo ───────────────────────────────────────────────────────────────────────────────────
def test_progression_case_is_preserved():
    assert infer_progression("C G Am F", "C Major") == "I - V - vi - IV"
    assert infer_progression("C G A F", "C Major") == "I - V - VI - IV"


def test_full_progression_keeps_order_and_repetitions():
    assert infer_progression_full("C G Am F C G Am F", "C Major") == ["I", "V", "vi", "IV"] * 2
    # un mismo acorde repetido seguido (una línea de la hoja) cuenta una sola vez
    assert infer_progression_full("C C C G G Am", "C Major") == ["I", "V", "vi"]
    assert infer_progression_full("", "C Major") == []


def test_pop_progression_needs_minor_sixth():
    # I-V-vi-IV suma Nostálgica por el patrón de pop emocional; I-V-VI-IV (VI mayor) no es ese patrón
    pop = style_scores("C G Am F C G Am F", "C Major")
    other = style_scores("C G A F C G A F", "C Major")
    assert pop["Nostálgica"] > other["Nostálgica"]


def test_brillante_is_scored_for_e_major():
    # E mayor tiene el color ["Brillante", "Enérgica"]: la etiqueta debe existir y puntuar
    assert style_scores("E A B C#m F#m G#m E A B", "E Major")["Brillante"] == 2


def test_flat_seventh_triggers_epic_pattern_in_major():
    # I-bVII-IV: el patrón "I ... VII" no puede ignorar el bVII por la b delante
    assert style_scores("D C G D C G D C G", "D Major")["Épica"] == 3


def test_modal_borrowing_not_triggered_by_ordinary_diatonic_mix():
    # C G Am F mezcla acordes mayores y menores pero todos son diatónicos: no es préstamo modal
    assert style_scores("C G Am F C G Am F", "C Major")["Cinematográfica"] == 0


def test_modal_borrowing_detects_iv_minor_in_major():
    # Fm (iv) en Do mayor es un acorde prestado del modo menor
    assert style_scores("C F Fm C G Am C F Fm", "C Major")["Cinematográfica"] >= 3


def test_loop_without_dominant_is_detected():
    # I-IV-vi no tiene dominante (antes la búsqueda de la letra V dentro de "IV"/"VI" lo impedía)
    assert style_scores("C F Am C F Am", "C Major")["Flotante"] >= 2
    assert style_scores("C F G Am C F G", "C Major")["Flotante"] == 0


def test_style_ranking_unchanged_shape():
    assert len(infer_emotional_style("C G Am F", "C Major").split(", ")) == 3
    assert infer_emotional_style("C G Am F", "") != ""


def test_patterns_must_be_consecutive():
    # ii-V-I seguido es jazz; los mismos grados dispersos en una canción larga no lo son
    assert style_scores("Dm G C Dm G C", "C Major")["Elegante"] >= 3
    assert style_scores("Dm C F C G C Dm C F G", "C Major")["Elegante"] == 0


def test_diminished_suffix_kept_when_numeral_has_no_degree_sign():
    assert get_roman_numeral("C", "Major", "Dbdim7") == "bIIdim7"
    assert get_roman_numeral("C", "Major", "Bdim7") == "vii°7"
