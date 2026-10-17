-- 046: fold_name() and resolve.fold() map the stroke and hook letters NFKD leaves whole.
--
-- Ħ Ŧ Ɨ Ƈ and their kin have no decomposition, so both folds dropped them: "ĿƗƇĦ" folded to "l" and "ŦūŦ" to "u". A
-- one-letter folded name is a substring of almost any question, so both players were offered at 0.7 ("name inside the
-- question") for "finals", "liquid" and "zeruhh per 10" - the junk candidate behind a share of the clarify answers.
-- Mapped to their base letter, they fold to "lich" and "tut". Python's table gains the same 48 letters
-- (tests/test_fold_parity.py holds the two equal). On production only those two names contain any of them, and no
-- anchor does, so nothing decided moves.

CREATE OR REPLACE FUNCTION fold_name(t text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT btrim(regexp_replace(regexp_replace(lower(translate(
        replace(replace(replace(replace(replace(replace(replace(replace(t,
            'ß', 'ss'), 'æ', 'ae'), 'Æ', 'AE'), 'œ', 'oe'), 'Œ', 'OE'), 'þ', 'th'), 'Þ', 'TH'), 'ð', 'd'),
        'ÀÁÂÃÄÅàáâãäåÈÉÊËèéêëÌÍÎÏìíîïÒÓÔÕÖØòóôõöøÙÚÛÜùúûüÝýÿÑñÇçŠšŽžĀāĒēĪīŌōŪūĂăĄąĆćĘęŁłŃńŚśŹźŻżĞğİıŞşĐđÐĿŀ'
        || 'ĦħŦŧƗɨƇƈƁɓƑƒƓɠƘƙƝɲƤƥƬƭƲʋƳƴƵƶƊɗƉɖŊŋɃƀɆɇɈɉɌɍɎɏȻȼȺⱥ',
        'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOOooooooUUUUuuuuYyyNnCcSsZzAaEeIiOoUuAaAaCcEeLlNnSsZzZzGgIiSsDdDLl'
        || 'HhTtIiCcBbFfGgKkNnPpTtVvYyZzDdDdNnBbEeJjRrYyCcAa')),
        '[^0-9a-z ]+', ' ', 'g'), '\s+', ' ', 'g'))
$$;
