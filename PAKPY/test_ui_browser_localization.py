import unittest
from types import SimpleNamespace

import msbt_codec
import ui_browser_localization as loc


def align(data, value=b'\xab'):
    return data + value * ((-len(data)) % 16)


def make_msbt(messages, byte_order='little', encoding_code=1):
    enc = 'utf-16-le' if byte_order == 'little' else 'utf-16-be'
    labels = bytearray()
    labels += (1).to_bytes(4, byte_order)
    bucket_data = bytearray()
    for index, (label, _text) in enumerate(messages):
        raw = label.encode('utf-8')
        bucket_data += bytes([len(raw)]) + raw + index.to_bytes(4, byte_order)
    labels += len(messages).to_bytes(4, byte_order)
    labels += (12).to_bytes(4, byte_order)
    labels += bucket_data

    text_data = bytearray()
    table_end = 4 + 4 * len(messages)
    offsets = []
    cursor = table_end
    for _label, text in messages:
        encoded = text.encode(enc) + b'\x00\x00'
        offsets.append(cursor)
        text_data += encoded
        cursor += len(encoded)
    txt = bytearray(len(messages).to_bytes(4, byte_order))
    txt += b''.join(value.to_bytes(4, byte_order) for value in offsets)
    txt += text_data
    atr = len(messages).to_bytes(4, byte_order) + (0).to_bytes(4, byte_order)

    sections = []
    for tag, payload in ((b'LBL1', labels), (b'ATR1', atr), (b'TXT2', txt)):
        head = tag + len(payload).to_bytes(4, byte_order) + b'\x00' * 8
        sections.append(align(head + payload))
    body = b''.join(sections)
    head = bytearray(32)
    head[:8] = b'MsgStdBn'
    head[8:10] = b'\xff\xfe' if byte_order == 'little' else b'\xfe\xff'
    head[12] = encoding_code
    head[13] = 3
    head[14:16] = (3).to_bytes(2, byte_order)
    head[18:22] = (32 + len(body)).to_bytes(4, byte_order)
    return bytes(head) + body


def record(language, bundle, label, text):
    return loc.LocalizationRecord('PAK', bundle, 'u', bundle, language, label, text, 0)


def catalog(records):
    by_lang = {}
    by_bundle = {}
    case = {}
    for item in records:
        by_lang.setdefault(item.language, {}).setdefault(item.label, []).append(item)
        by_bundle.setdefault((item.bundle.casefold(), item.language), {}).setdefault(item.label, []).append(item)
        case[item.label.casefold()] = item.label
    return {
        'records': tuple(records), 'errors': (), 'documents': (),
        'languages': tuple(dict.fromkeys(item.language for item in records)),
        'by_language': {k: {x: tuple(y) for x, y in v.items()} for k, v in by_lang.items()},
        'by_bundle_language': {k: {x: tuple(y) for x, y in v.items()} for k, v in by_bundle.items()},
        'casefold_labels': case,
    }


class MsbtCodecTests(unittest.TestCase):
    def test_parses_little_endian_utf16_labels_and_texts(self):
        doc = msbt_codec.parse_msbt(make_msbt([('Hello', 'Hello world'), ('Line', 'A\nB')]))
        self.assertEqual(doc.byte_order, 'little')
        self.assertEqual(doc.by_label['Hello'].text, 'Hello world')
        self.assertEqual(doc.messages[1].text, 'A\nB')

    def test_parses_big_endian_utf16(self):
        doc = msbt_codec.parse_msbt(make_msbt([('Hello', 'Grüße')], 'big'))
        self.assertEqual(doc.byte_order, 'big')
        self.assertEqual(doc.messages[0].text, 'Grüße')

    def test_preserves_open_and_close_control_tags(self):
        raw = (
            "A".encode("utf-16-le")
            + (0x000E).to_bytes(2, "little")
            + (1).to_bytes(2, "little")
            + (2).to_bytes(2, "little")
            + (2).to_bytes(2, "little")
            + b"\x34\x12"
            + "B".encode("utf-16-le")
            + (0x000F).to_bytes(2, "little")
            + (1).to_bytes(2, "little")
            + (2).to_bytes(2, "little")
        )
        self.assertEqual(
            msbt_codec._decode_utf16_message(raw, "little", "utf-16-le"),
            "A<tag:1:2:3412>B</tag:1:2>",
        )

    def test_rejects_truncated_section(self):
        with self.assertRaises(msbt_codec.MsbtError):
            msbt_codec.parse_msbt(make_msbt([('A', 'B')])[:-5])


class LocalizationTests(unittest.TestCase):
    def movie(self, records, language='EUGE', fallback='USEN'):
        return SimpleNamespace(
            ui_localization_catalog=catalog(records), ui_localization_enabled=True,
            ui_localization_language=language, ui_localization_fallback=fallback,
            avm2_modules=(), definitions={}, ui_native_callback_summaries=(),
        )

    def test_selected_language_and_fallback(self):
        movie = self.movie([
            record('USEN', 'shell', 'Start', 'PRESS START'),
            record('EUGE', 'shell', 'Start', 'START DRÜCKEN'),
            record('USEN', 'shell', 'OnlyEnglish', 'ONLY ENGLISH'),
        ])
        self.assertEqual(loc.resolve_text_id(movie, 'Start').text, 'START DRÜCKEN')
        result = loc.resolve_text_id(movie, 'OnlyEnglish')
        self.assertEqual(result.text, 'ONLY ENGLISH')
        self.assertTrue(result.fallback_used)

    def test_wrapped_and_prefixed_ids(self):
        movie = self.movie([record('EUGE', 'shell', 'Options_Audio', 'AUDIO')])
        self.assertEqual(loc.localize_value(movie, '${Options_Audio}'), 'AUDIO')
        self.assertEqual(loc.localize_value(movie, 'msbt:Options_Audio'), 'AUDIO')

    def test_ambiguous_cross_bundle_label_is_not_guessed(self):
        movie = self.movie([
            record('EUGE', 'saveslot', 'l01', '1-1'),
            record('EUGE', 'universe', 'l01', 'MANGROVENBUCHT'),
        ])
        self.assertIsNone(loc.resolve_text_id(movie, 'l01'))
        self.assertEqual(loc.resolve_text_id(movie, 'universe:l01').text, 'MANGROVENBUCHT')

    def test_identical_duplicate_text_is_safe(self):
        movie = self.movie([
            record('EUGE', 'one', 'Same', 'GLEICH'),
            record('EUGE', 'two', 'Same', 'GLEICH'),
        ])
        self.assertEqual(loc.resolve_text_id(movie, 'Same').text, 'GLEICH')

    def test_disabled_localization_preserves_id(self):
        movie = self.movie([record('EUGE', 'shell', 'Start', 'START')])
        movie.ui_localization_enabled = False
        self.assertEqual(loc.localize_value(movie, 'Start'), 'Start')

    def test_config_is_bounded_to_available_languages(self):
        result = loc.normalize_localization_config(
            {'language': 'NOPE', 'fallback': 'BAD', 'enabled': True}, ('USEN', 'EUGE')
        )
        self.assertEqual(result['language'], 'USEN')
        self.assertEqual(result['fallback'], 'USEN')


if __name__ == '__main__':
    unittest.main()
