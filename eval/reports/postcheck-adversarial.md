# Post-check adversarial set (CW-619)

Scripted bad generate outputs against synthetic chunks, run through the real
pipeline with a scripted LLM (no model calls, no cost). Regenerate with
`uv run python -m eval.postcheck`; `tests/test_postcheck_adversarial.py` fails
when this report and `eval/postcheck_cases.yaml` disagree.

- **Bad answers caught:** 14/23
- **Clean controls left clean:** 7/7

| Kind | Caught |
|---|---|
| outside_brand | 2/3 |
| hebrew_prefix | 2/3 |
| corpus_car | 1/1 |
| sibling_model | 1/3 |
| brandless_model | 0/1 |
| alias_collision | 4/4 |
| invented_number | 3/3 |
| rewrite_number | 1/1 |
| number_precision | 0/2 |
| cross_car_number | 0/1 |
| number_words | 0/1 |

## Known misses

| Case | Kind | Why not caught |
|---|---|---|
| `outside-brand-not-listed` | outside_brand | a brand missing from guardrails.outside_brands is not seen |
| `prefix-stacked-short-brand` | hebrew_prefix | a short brand after two prefixes ('ולרנו') is given up on purpose (CW-602) |
| `sibling-kia-ev6` | sibling_model | CR-004: another model of a corpus brand (Kia EV6) is not caught |
| `sibling-kia-sorento` | sibling_model | CR-004: another model of a corpus brand, with no digit in its name, is not caught |
| `brandless-model` | brandless_model | CR-004: a model name with no brand and no registry alias (Camry) is not caught |
| `truncated-decimal` | number_precision | CR-009(a): truncation is accepted, so a source 5.9 backs an answer of 5 |
| `small-count-from-another-attribute` | number_precision | CR-009(c): a small count is backed by any chunk number (7 hours backs 7 seats) |
| `cross-car-number-swap` | cross_car_number | CR-009(b): the check is per value, not per car; swapped figures pass |
| `number-as-words` | number_words | README Known limitations: numbers written as words are not checked |

## All cases

| Case | Kind | Bad | Flagged by | Outcome | Note |
|---|---|---|---|---|---|
| `outside-brand-hebrew` | outside_brand | yes | cars | fallback |  |
| `outside-brand-latin` | outside_brand | yes | cars | fallback |  |
| `outside-brand-not-listed` | outside_brand | yes | - | clean | a brand missing from guardrails.outside_brands is not seen |
| `prefix-stacked-long-brand` | hebrew_prefix | yes | cars | fallback |  |
| `prefix-on-corpus-car` | hebrew_prefix | yes | cars | fallback |  |
| `prefix-stacked-short-brand` | hebrew_prefix | yes | - | clean | a short brand after two prefixes ('ולרנו') is given up on purpose (CW-602) |
| `corpus-car-not-retrieved` | corpus_car | yes | cars | fallback |  |
| `sibling-kia-ev6` | sibling_model | yes | - | clean | CR-004: another model of a corpus brand (Kia EV6) is not caught |
| `sibling-kia-sorento` | sibling_model | yes | - | clean | CR-004: another model of a corpus brand, with no digit in its name, is not caught |
| `sibling-ioniq-5` | sibling_model | yes | numbers | fallback | CR-004 still holds for the name; only the numeric check fires, because no chunk states 5 |
| `brandless-model` | brandless_model | yes | - | clean | CR-004: a model name with no brand and no registry alias (Camry) is not caught |
| `alias-audi-s6` | alias_collision | yes | cars | fallback |  |
| `alias-c3-aircross` | alias_collision | yes | cars | fallback |  |
| `alias-elantra-hybrid` | alias_collision | yes | cars | fallback |  |
| `alias-aion-y` | alias_collision | yes | cars | fallback |  |
| `invented-price` | invented_number | yes | numbers | fallback |  |
| `invented-range` | invented_number | yes | numbers | fallback |  |
| `invented-power` | invented_number | yes | numbers | fallback |  |
| `number-only-in-rewrite` | rewrite_number | yes | numbers | fallback |  |
| `truncated-decimal` | number_precision | yes | - | clean | CR-009(a): truncation is accepted, so a source 5.9 backs an answer of 5 |
| `small-count-from-another-attribute` | number_precision | yes | - | clean | CR-009(c): a small count is backed by any chunk number (7 hours backs 7 seats) |
| `cross-car-number-swap` | cross_car_number | yes | - | clean | CR-009(b): the check is per value, not per car; swapped figures pass |
| `number-as-words` | number_words | yes | - | clean | README Known limitations: numbers written as words are not checked |
| `control-rival-in-chunk` | control | no | - | clean |  |
| `control-user-number` | control | no | - | clean |  |
| `control-rounded-price` | control | no | - | clean |  |
| `control-decimal-comma` | control | no | - | clean |  |
| `control-difference-of-stated-numbers` | control | no | - | clean |  |
| `control-asked-outside-car` | control | no | - | clean |  |
| `control-prefixes-and-plural-verbs` | control | no | - | clean |  |
