-- 040: SQL fold_name() folds exactly as Python's resolve.fold() does.
--
-- Team-map anchors (entity_anchors.anchor) are written with Python's fold, which turns every run of punctuation into
-- one space ("Virtus.pro" -> "virtus pro"), and looked up in SQL with fold_name(), which kept the punctuation
-- ("virtus.pro"). So a Liquipedia name with a dot, an apostrophe, a hyphen or a parenthesis never met its anchor in
-- the series view, the placements view, the searchable names or the checks: Virtus.pro, Anyone's Legend and
-- Supernova (American team) on production, and Team CC (Chinese orgless team) and LGD.OA in Stage 4 - a decided name
-- whose Liquipedia-only series silently stayed out of every answer. Found by golden case G61 (T1's record at the 2025
-- World Finals counted 4 of its 5 series: the fifth was against Team CC).
--
-- Same steps as Python: the letters NFKD cannot strip mapped first (ł ø đ ß æ œ ı þ ð), accents stripped, lower case,
-- every run of characters outside [0-9a-z ] to one space, whitespace collapsed, trimmed. tests/test_fold_parity.py
-- holds the two to the same output. IMMUTABLE as before; the materialized views pick it up on the next refresh.

CREATE OR REPLACE FUNCTION fold_name(t text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT btrim(regexp_replace(regexp_replace(lower(translate(
        replace(replace(replace(replace(replace(replace(replace(replace(t,
            'ß', 'ss'), 'æ', 'ae'), 'Æ', 'AE'), 'œ', 'oe'), 'Œ', 'OE'), 'þ', 'th'), 'Þ', 'TH'), 'ð', 'd'),
        'ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖØòóôõöøÙÚÛÜùúûüÝýÿÑñÇçŠšŽžĀāĒēĪīŌōŪūĂăĄąĆćĘęŁłŃńŚśŹźŻżĞğİıŞşĐđÐĿŀ',
        'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOOooooooUUUUuuuuYyyNnCcSsZzAaEeIiOoUuAaAaCcEeLlNnSsZzZzGgIiSsDdDLl')),
        '[^0-9a-z ]+', ' ', 'g'), '\s+', ' ', 'g'))
$$;
