from src.services.chord_analyzer import ChordAnalyzer

def test_progression(name, chords_str):
    print("=" * 60)
    print(f"TESTING PROGRESSION: {name}")
    print(f"Raw chords: {chords_str}")
    print("-" * 60)
    
    result = ChordAnalyzer.analyze(chords_str)
    print(f"Tonality:    {result['Tonality']}")
    print(f"Progression: {result['Progression']}")
    print(f"Complexity:  {result['Complex']}")
    print(f"Style:       {result['Style']}")
    print("=" * 60 + "\n")
    return result

def main():
    # Test 1: Simple Pop/Rock mixolydian loop with slash chords
    r1 = test_progression(
        "Simple Mixolydian (E D A/Cs)",
        "<intro_1> E D A/Cs E D A/Cs <verse_1> E D A/Cs E D A/Cs"
    )
    assert r1['Tonality'] in ("E Major", "A Major"), f"Unexpected key: {r1['Tonality']}"
    assert "I" in r1['Progression'], "Expected tonic Roman numeral"
    
    # Test 2: Standard minor chord loop
    r2 = test_progression(
        "Standard Minor Loop (C# minor)",
        "<intro_1> Csmin Csmin <verse_1> A Csmin A Csmin Fsmin B Csmin"
    )
    assert r2['Tonality'] == "C# Minor", f"Unexpected key: {r2['Tonality']}"
    assert "i" in r2['Progression'], "Expected tonic minor Roman numeral"
    assert r2['Style'] == "Oscura", f"Unexpected style: {r2['Style']}"

    # Test 3: Simple major triads
    r3 = test_progression(
        "Simple Major Triads (C F G)",
        "C F G C"
    )
    assert r3['Tonality'] == "C Major", f"Unexpected key: {r3['Tonality']}"
    assert r3['Progression'] == "I - IV - V - I", f"Unexpected progression: {r3['Progression']}"
    assert r3['Complex'] == "Baja", f"Unexpected complexity: {r3['Complex']}"
    assert r3['Style'] == "simple", f"Unexpected style: {r3['Style']}"

    # Test 4: Extended Jazz/Pop chords
    r4 = test_progression(
        "Extended Jazz/Pop Chords",
        "Cmaj7 Fmaj7 Dmin7 G7 Cmaj7"
    )
    assert r4['Tonality'] == "C Major", f"Unexpected key: {r4['Tonality']}"
    assert r4['Progression'] == "Imaj7 - IVmaj7 - ii7 - V7 - Imaj7", f"Unexpected progression: {r4['Progression']}"
    assert r4['Complex'] in ("Media", "Media-Alta", "Alta"), f"Unexpected complexity: {r4['Complex']}"
    assert r4['Style'] == "moderna", f"Unexpected style: {r4['Style']}"

    print("🎉 ALL HARMONIC ENGINE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
