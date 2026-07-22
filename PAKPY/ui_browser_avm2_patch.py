"""Parse AVM2 ABC modules and execute a deliberately small safe frame-script subset.

The patch inventories DoABC blocks, parses the complete structural ABC tables used by
Scaleform movies, exposes classes/methods/frame scripts in a dedicated inspector and
executes only directly identifiable timeline calls: stop, play, gotoAndStop and
gotoAndPlay. It is not a general ActionScript VM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import struct
import tkinter as tk
from tkinter import filedialog, ttk

import ui_browser
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core


TAG_DO_ABC = 82
_INSTALLED = False
_BASE_PARSE_SWF = None
_BASE_INSPECT_MOVIE_STATE = None
_BASE_FORMAT_STATE_NODE = None
_BASE_BROWSER_INIT = None
_BASE_BROWSER_TREE_SELECT = None
_BASE_BROWSER_FORMAT_INFO = None
_BASE_BROWSER_CLOSE = None
_BASE_BROWSER_RENDER = None
_BASE_TIMELINE_FRAME_FOR_PATH = None
_BASE_TIMELINE_ADVANCE = None
_BASE_TIMELINE_PLAY = None
_BASE_TIMELINE_PAUSE = None


class ABCParseError(Exception):
    pass


class ABCReader:
    def __init__(self, data, offset=0):
        self.data = bytes(data)
        self.offset = int(offset)

    @property
    def remaining(self):
        return len(self.data) - self.offset

    def require(self, count):
        if count < 0 or self.offset + count > len(self.data):
            raise ABCParseError("ABC-Daten sind abgeschnitten")

    def read_u8(self):
        self.require(1)
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_s8(self):
        value = self.read_u8()
        return value - 256 if value & 0x80 else value

    def read_u16(self):
        self.require(2)
        value = int.from_bytes(self.data[self.offset:self.offset + 2], "little")
        self.offset += 2
        return value

    def read_u32le(self):
        self.require(4)
        value = int.from_bytes(self.data[self.offset:self.offset + 4], "little")
        self.offset += 4
        return value

    def read_s24(self):
        self.require(3)
        value = int.from_bytes(self.data[self.offset:self.offset + 3], "little")
        self.offset += 3
        return value - 0x1000000 if value & 0x800000 else value

    def read_u32(self):
        result = 0
        shift = 0
        for index in range(5):
            byte = self.read_u8()
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return result & 0xFFFFFFFF
            shift += 7
        return result & 0xFFFFFFFF

    def read_u30(self):
        value = self.read_u32()
        if value > 0x3FFFFFFF:
            raise ABCParseError(f"Ungültiger U30-Wert {value}")
        return value

    def read_s32(self):
        value = self.read_u32()
        return value - 0x100000000 if value & 0x80000000 else value

    def read_double(self):
        self.require(8)
        value = struct.unpack_from("<d", self.data, self.offset)[0]
        self.offset += 8
        return value

    def read_bytes(self, count):
        self.require(count)
        value = self.data[self.offset:self.offset + count]
        self.offset += count
        return value


@dataclass(frozen=True)
class ABCNamespace:
    kind: int
    name_index: int


@dataclass(frozen=True)
class ABCMultiname:
    kind: int
    namespace_index: int = 0
    name_index: int = 0
    namespace_set_index: int = 0
    type_name_index: int = 0
    type_parameters: tuple[int, ...] = ()


@dataclass(frozen=True)
class ABCTrait:
    name_index: int
    kind: int
    attributes: int
    slot_id: int = 0
    type_name_index: int = 0
    value_index: int = 0
    value_kind: int = 0
    dispatch_id: int = 0
    method_index: int = -1
    class_index: int = -1
    function_index: int = -1
    metadata: tuple[int, ...] = ()


@dataclass(frozen=True)
class ABCMethod:
    parameter_types: tuple[int, ...]
    return_type: int
    name_index: int
    flags: int
    optional_values: tuple[tuple[int, int], ...] = ()
    parameter_names: tuple[int, ...] = ()


@dataclass(frozen=True)
class ABCMetadata:
    name_index: int
    items: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ABCInstance:
    name_index: int
    super_name_index: int
    flags: int
    protected_namespace: int
    interfaces: tuple[int, ...]
    initializer: int
    traits: tuple[ABCTrait, ...]


@dataclass(frozen=True)
class ABCClass:
    initializer: int
    traits: tuple[ABCTrait, ...]


@dataclass(frozen=True)
class ABCScript:
    initializer: int
    traits: tuple[ABCTrait, ...]


@dataclass(frozen=True)
class ABCException:
    start: int
    end: int
    target: int
    type_index: int
    variable_name_index: int


@dataclass(frozen=True)
class ABCMethodBody:
    method_index: int
    max_stack: int
    local_count: int
    init_scope_depth: int
    max_scope_depth: int
    code: bytes
    exceptions: tuple[ABCException, ...]
    traits: tuple[ABCTrait, ...]


@dataclass
class ABCFile:
    minor_version: int
    major_version: int
    ints: tuple[int, ...]
    uints: tuple[int, ...]
    doubles: tuple[float, ...]
    strings: tuple[str, ...]
    namespaces: tuple[ABCNamespace | None, ...]
    namespace_sets: tuple[tuple[int, ...], ...]
    multinames: tuple[ABCMultiname | None, ...]
    methods: tuple[ABCMethod, ...]
    metadata: tuple[ABCMetadata, ...]
    instances: tuple[ABCInstance, ...]
    classes: tuple[ABCClass, ...]
    scripts: tuple[ABCScript, ...]
    method_bodies: tuple[ABCMethodBody, ...]
    trailing_bytes: bytes = b""
    _body_by_method: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self._body_by_method = {body.method_index: body for body in self.method_bodies}

    def string(self, index):
        return self.strings[index] if 0 <= int(index) < len(self.strings) else ""

    def namespace_name(self, index):
        if not (0 < int(index) < len(self.namespaces)):
            return ""
        namespace = self.namespaces[int(index)]
        return self.string(namespace.name_index) if namespace is not None else ""

    def multiname_name(self, index):
        index = int(index)
        if not (0 < index < len(self.multinames)):
            return "*" if index == 0 else f"multiname#{index}"
        value = self.multinames[index]
        if value is None:
            return "*"
        kind = value.kind
        name = self.string(value.name_index)
        if kind in (0x07, 0x0D):
            namespace = self.namespace_name(value.namespace_index)
            return f"{namespace}.{name}" if namespace else name
        if kind in (0x0F, 0x10, 0x11, 0x12):
            return name or "<runtime-name>"
        if kind in (0x09, 0x0E, 0x1B, 0x1C):
            return name or "<multiname-late>"
        if kind == 0x1D:
            base = self.multiname_name(value.type_name_index)
            parameters = ", ".join(self.multiname_name(item) for item in value.type_parameters)
            return f"{base}.<{parameters}>"
        return name or f"multiname#{index}"

    def method_name(self, index):
        if not (0 <= int(index) < len(self.methods)):
            return f"method#{index}"
        name = self.string(self.methods[int(index)].name_index)
        return name or f"method#{index}"

    def class_name(self, index):
        if not (0 <= int(index) < len(self.instances)):
            return f"class#{index}"
        return self.multiname_name(self.instances[int(index)].name_index)

    def method_body(self, index):
        return self._body_by_method.get(int(index))


@dataclass(frozen=True)
class ABCModule:
    flags: int
    name: str
    source: str
    raw_size: int
    abc: ABCFile | None
    error: str = ""


@dataclass(frozen=True)
class AVM2Instruction:
    offset: int
    opcode: int
    name: str
    operands: tuple
    size: int


@dataclass(frozen=True)
class TimelineAction:
    operation: str
    target: object | None = None


@dataclass(frozen=True)
class FrameScriptBinding:
    class_name: str
    frame: int
    method_index: int
    method_name: str
    actions: tuple[TimelineAction, ...]
    module_name: str = ""


_MAX_POOL_ENTRIES = 1_000_000


def _pool_count(reader, label):
    count = reader.read_u30()
    if count > _MAX_POOL_ENTRIES:
        raise ABCParseError(f"ABC-{label}-Pool ist unrealistisch groß: {count}")
    return count


def _read_index_pool(reader, item_reader, default):
    count = _pool_count(reader, "Konstanten")
    values = [default]
    for _ in range(max(0, count - 1)):
        values.append(item_reader())
    return tuple(values)


def _read_traits(reader):
    count = _pool_count(reader, "Trait")
    result = []
    for _ in range(count):
        name_index = reader.read_u30()
        kind_attr = reader.read_u8()
        kind = kind_attr & 0x0F
        attributes = kind_attr >> 4
        values = {
            "slot_id": 0, "type_name_index": 0, "value_index": 0,
            "value_kind": 0, "dispatch_id": 0, "method_index": -1,
            "class_index": -1, "function_index": -1,
        }
        if kind in (0, 6):
            values["slot_id"] = reader.read_u30()
            values["type_name_index"] = reader.read_u30()
            values["value_index"] = reader.read_u30()
            if values["value_index"]:
                values["value_kind"] = reader.read_u8()
        elif kind in (1, 2, 3):
            values["dispatch_id"] = reader.read_u30()
            values["method_index"] = reader.read_u30()
        elif kind == 4:
            values["slot_id"] = reader.read_u30()
            values["class_index"] = reader.read_u30()
        elif kind == 5:
            values["slot_id"] = reader.read_u30()
            values["function_index"] = reader.read_u30()
        else:
            raise ABCParseError(f"Unbekannter ABC-Trait-Typ {kind}")
        metadata = ()
        if attributes & 0x04:
            metadata = tuple(reader.read_u30() for _ in range(_pool_count(reader, "Trait-Metadaten")))
        result.append(ABCTrait(name_index, kind, attributes, metadata=metadata, **values))
    return tuple(result)


def parse_abc(data):
    reader = ABCReader(data)
    minor = reader.read_u16()
    major = reader.read_u16()
    ints = _read_index_pool(reader, reader.read_s32, 0)
    uints = _read_index_pool(reader, reader.read_u32, 0)
    doubles = _read_index_pool(reader, reader.read_double, float("nan"))

    string_count = _pool_count(reader, "String")
    strings = [""]
    for _ in range(max(0, string_count - 1)):
        raw = reader.read_bytes(reader.read_u30())
        strings.append(raw.decode("utf-8", "replace"))

    namespace_count = _pool_count(reader, "Namespace")
    namespaces = [None]
    for _ in range(max(0, namespace_count - 1)):
        namespaces.append(ABCNamespace(reader.read_u8(), reader.read_u30()))

    namespace_set_count = _pool_count(reader, "Namespace-Set")
    namespace_sets = [()]
    for _ in range(max(0, namespace_set_count - 1)):
        namespace_sets.append(tuple(reader.read_u30() for _ in range(_pool_count(reader, "Namespace-Set-Eintrag"))))

    multiname_count = _pool_count(reader, "Multiname")
    multinames = [None]
    for _ in range(max(0, multiname_count - 1)):
        kind = reader.read_u8()
        if kind in (0x07, 0x0D):
            value = ABCMultiname(kind, reader.read_u30(), reader.read_u30())
        elif kind in (0x0F, 0x10):
            value = ABCMultiname(kind, name_index=reader.read_u30())
        elif kind in (0x11, 0x12):
            value = ABCMultiname(kind)
        elif kind in (0x09, 0x0E):
            value = ABCMultiname(kind, name_index=reader.read_u30(), namespace_set_index=reader.read_u30())
        elif kind in (0x1B, 0x1C):
            value = ABCMultiname(kind, namespace_set_index=reader.read_u30())
        elif kind == 0x1D:
            base = reader.read_u30()
            parameters = tuple(reader.read_u30() for _ in range(_pool_count(reader, "TypeName-Parameter")))
            value = ABCMultiname(kind, type_name_index=base, type_parameters=parameters)
        else:
            raise ABCParseError(f"Unbekannter Multiname-Typ 0x{kind:02X}")
        multinames.append(value)

    methods = []
    for _ in range(_pool_count(reader, "Methoden")):
        parameter_count = _pool_count(reader, "Methodenparameter")
        return_type = reader.read_u30()
        parameter_types = tuple(reader.read_u30() for _ in range(parameter_count))
        name_index = reader.read_u30()
        flags = reader.read_u8()
        optional = ()
        if flags & 0x08:
            optional = tuple((reader.read_u30(), reader.read_u8()) for _ in range(_pool_count(reader, "optionale Parameter")))
        parameter_names = ()
        if flags & 0x80:
            parameter_names = tuple(reader.read_u30() for _ in range(parameter_count))
        methods.append(ABCMethod(parameter_types, return_type, name_index, flags, optional, parameter_names))

    metadata = []
    for _ in range(_pool_count(reader, "Metadaten")):
        name_index = reader.read_u30()
        item_count = _pool_count(reader, "Metadaten-Einträge")
        keys = [reader.read_u30() for _ in range(item_count)]
        values = [reader.read_u30() for _ in range(item_count)]
        metadata.append(ABCMetadata(name_index, tuple(zip(keys, values))))

    class_count = _pool_count(reader, "Klassen")
    instances = []
    for _ in range(class_count):
        name_index = reader.read_u30()
        super_name_index = reader.read_u30()
        flags = reader.read_u8()
        protected_namespace = reader.read_u30() if flags & 0x08 else 0
        interfaces = tuple(reader.read_u30() for _ in range(_pool_count(reader, "Interfaces")))
        initializer = reader.read_u30()
        instances.append(ABCInstance(
            name_index, super_name_index, flags, protected_namespace,
            interfaces, initializer, _read_traits(reader),
        ))

    classes = []
    for _ in range(class_count):
        classes.append(ABCClass(reader.read_u30(), _read_traits(reader)))

    scripts = []
    for _ in range(_pool_count(reader, "Scripts")):
        scripts.append(ABCScript(reader.read_u30(), _read_traits(reader)))

    bodies = []
    for _ in range(_pool_count(reader, "Methodenbodies")):
        method_index = reader.read_u30()
        max_stack = reader.read_u30()
        local_count = reader.read_u30()
        init_scope = reader.read_u30()
        max_scope = reader.read_u30()
        code = reader.read_bytes(reader.read_u30())
        exceptions = []
        for _ in range(_pool_count(reader, "Exceptions")):
            exceptions.append(ABCException(
                reader.read_u30(), reader.read_u30(), reader.read_u30(),
                reader.read_u30(), reader.read_u30(),
            ))
        bodies.append(ABCMethodBody(
            method_index, max_stack, local_count, init_scope, max_scope,
            code, tuple(exceptions), _read_traits(reader),
        ))

    return ABCFile(
        minor, major, ints, uints, doubles, tuple(strings), tuple(namespaces),
        tuple(namespace_sets), tuple(multinames), tuple(methods), tuple(metadata),
        tuple(instances), tuple(classes), tuple(scripts), tuple(bodies),
        reader.read_bytes(reader.remaining) if reader.remaining else b"",
    )


def parse_doabc(payload, source="root"):
    payload = bytes(payload)
    if len(payload) < 5:
        raise ABCParseError("DoABC-Tag ist abgeschnitten")
    flags = int.from_bytes(payload[:4], "little")
    end = payload.find(b"\x00", 4)
    if end < 0:
        raise ABCParseError("DoABC-Modulname ist nicht nullterminiert")
    name = payload[4:end].decode("utf-8", "replace")
    abc_data = payload[end + 1:]
    try:
        abc = parse_abc(abc_data)
        return ABCModule(flags, name or "<unbenannt>", source, len(abc_data), abc, "")
    except Exception as exc:
        return ABCModule(flags, name or "<unbenannt>", source, len(abc_data), None, str(exc))


_OPCODES = {
    0x01:("bkpt",()), 0x02:("nop",()), 0x03:("throw",()),
    0x04:("getsuper",("mn",)), 0x05:("setsuper",("mn",)), 0x06:("dxns",("string",)),
    0x07:("dxnslate",()), 0x08:("kill",("u30",)), 0x09:("label",()),
    0x0C:("ifnlt",("s24",)), 0x0D:("ifnle",("s24",)), 0x0E:("ifngt",("s24",)),
    0x0F:("ifnge",("s24",)), 0x10:("jump",("s24",)), 0x11:("iftrue",("s24",)),
    0x12:("iffalse",("s24",)), 0x13:("ifeq",("s24",)), 0x14:("ifne",("s24",)),
    0x15:("iflt",("s24",)), 0x16:("ifle",("s24",)), 0x17:("ifgt",("s24",)),
    0x18:("ifge",("s24",)), 0x19:("ifstricteq",("s24",)), 0x1A:("ifstrictne",("s24",)),
    0x1B:("lookupswitch",("switch",)), 0x1C:("pushwith",()), 0x1D:("popscope",()),
    0x1E:("nextname",()), 0x1F:("hasnext",()), 0x20:("pushnull",()),
    0x21:("pushundefined",()), 0x23:("nextvalue",()), 0x24:("pushbyte",("s8",)),
    0x25:("pushshort",("u30",)), 0x26:("pushtrue",()), 0x27:("pushfalse",()),
    0x28:("pushnan",()), 0x29:("pop",()), 0x2A:("dup",()), 0x2B:("swap",()),
    0x2C:("pushstring",("string",)), 0x2D:("pushint",("int",)),
    0x2E:("pushuint",("uint",)), 0x2F:("pushdouble",("double",)),
    0x30:("pushscope",()), 0x31:("pushnamespace",("namespace",)),
    0x32:("hasnext2",("u30","u30")), 0x35:("li8",()), 0x36:("li16",()),
    0x37:("li32",()), 0x38:("lf32",()), 0x39:("lf64",()), 0x3A:("si8",()),
    0x3B:("si16",()), 0x3C:("si32",()), 0x3D:("sf32",()), 0x3E:("sf64",()),
    0x40:("newfunction",("method",)), 0x41:("call",("argc",)), 0x42:("construct",("argc",)),
    0x43:("callmethod",("method","argc")), 0x44:("callstatic",("method","argc")),
    0x45:("callsuper",("mn","argc")), 0x46:("callproperty",("mn","argc")),
    0x47:("returnvoid",()), 0x48:("returnvalue",()), 0x49:("constructsuper",("argc",)),
    0x4A:("constructprop",("mn","argc")), 0x4B:("callsuperid",("u30","argc")),
    0x4C:("callproplex",("mn","argc")), 0x4D:("callinterface",("u30","argc")),
    0x4E:("callsupervoid",("mn","argc")), 0x4F:("callpropvoid",("mn","argc")),
    0x50:("sxi1",()), 0x51:("sxi8",()), 0x52:("sxi16",()), 0x53:("applytype",("argc",)),
    0x55:("newobject",("argc",)), 0x56:("newarray",("argc",)), 0x57:("newactivation",()),
    0x58:("newclass",("class",)), 0x59:("getdescendants",("mn",)), 0x5A:("newcatch",("u30",)),
    0x5B:("findpropglobalstrict",("mn",)), 0x5C:("findpropglobal",("mn",)),
    0x5D:("findpropstrict",("mn",)), 0x5E:("findproperty",("mn",)), 0x5F:("finddef",("mn",)),
    0x60:("getlex",("mn",)), 0x61:("setproperty",("mn",)), 0x62:("getlocal",("u30",)),
    0x63:("setlocal",("u30",)), 0x64:("getglobalscope",()), 0x65:("getscopeobject",("u8",)),
    0x66:("getproperty",("mn",)), 0x67:("getouterscope",("u30",)), 0x68:("initproperty",("mn",)),
    0x69:("setpropertylate",()), 0x6A:("deleteproperty",("mn",)), 0x6B:("deletepropertylate",()),
    0x6C:("getslot",("u30",)), 0x6D:("setslot",("u30",)), 0x6E:("getglobalslot",("u30",)),
    0x6F:("setglobalslot",("u30",)), 0x70:("convert_s",()), 0x71:("esc_xelem",()),
    0x72:("esc_xattr",()), 0x73:("convert_i",()), 0x74:("convert_u",()), 0x75:("convert_d",()),
    0x76:("convert_b",()), 0x77:("convert_o",()), 0x78:("checkfilter",()),
    0x79:("convert_m",()), 0x7A:("convert_m_p",("u30",)), 0x80:("coerce",("mn",)),
    0x81:("coerce_b",()), 0x82:("coerce_a",()), 0x83:("coerce_i",()), 0x84:("coerce_d",()),
    0x85:("coerce_s",()), 0x86:("astype",("mn",)), 0x87:("astypelate",()),
    0x88:("coerce_u",()), 0x89:("coerce_o",()), 0x90:("negate",()), 0x91:("increment",()),
    0x92:("inclocal",("u30",)), 0x93:("decrement",()), 0x94:("declocal",("u30",)),
    0x95:("typeof",()), 0x96:("not",()), 0x97:("bitnot",()), 0xA0:("add",()),
    0xA1:("subtract",()), 0xA2:("multiply",()), 0xA3:("divide",()), 0xA4:("modulo",()),
    0xA5:("lshift",()), 0xA6:("rshift",()), 0xA7:("urshift",()), 0xA8:("bitand",()),
    0xA9:("bitor",()), 0xAA:("bitxor",()), 0xAB:("equals",()), 0xAC:("strictequals",()),
    0xAD:("lessthan",()), 0xAE:("lessequals",()), 0xAF:("greaterthan",()),
    0xB0:("greaterequals",()), 0xB1:("instanceof",()), 0xB2:("istype",("mn",)),
    0xB3:("istypelate",()), 0xB4:("in",()), 0xC0:("increment_i",()),
    0xC1:("decrement_i",()), 0xC2:("inclocal_i",("u30",)), 0xC3:("declocal_i",("u30",)),
    0xC4:("negate_i",()), 0xC5:("add_i",()), 0xC6:("subtract_i",()), 0xC7:("multiply_i",()),
    0xD0:("getlocal_0",()), 0xD1:("getlocal_1",()), 0xD2:("getlocal_2",()),
    0xD3:("getlocal_3",()), 0xD4:("setlocal_0",()), 0xD5:("setlocal_1",()),
    0xD6:("setlocal_2",()), 0xD7:("setlocal_3",()),
    0xEF:("debug",("u8","string","u8","u30")), 0xF0:("debugline",("u30",)),
    0xF1:("debugfile",("string",)), 0xF2:("bkptline",("u30",)),
}


def _read_operand(reader, kind):
    if kind in ("u30", "argc", "mn", "string", "int", "uint", "double", "namespace", "method", "class"):
        return reader.read_u30()
    if kind == "u8":
        return reader.read_u8()
    if kind == "s8":
        return reader.read_s8()
    if kind == "s24":
        return reader.read_s24()
    raise ABCParseError(f"Unbekannter Opcode-Operand {kind}")


def disassemble_code(code):
    reader = ABCReader(code)
    result = []
    while reader.remaining > 0:
        start = reader.offset
        opcode = reader.read_u8()
        name, schema = _OPCODES.get(opcode, (f"op_{opcode:02X}", ()))
        operands = []
        try:
            for kind in schema:
                if kind == "switch":
                    default = reader.read_s24()
                    case_count = reader.read_u30()
                    cases = tuple(reader.read_s24() for _ in range(case_count + 1))
                    operands.append((default, cases))
                else:
                    operands.append(_read_operand(reader, kind))
        except Exception:
            result.append(AVM2Instruction(start, opcode, name + " <abgeschnitten>", tuple(operands), reader.offset - start))
            break
        result.append(AVM2Instruction(start, opcode, name, tuple(operands), reader.offset - start))
    return tuple(result)


def disassemble_method(abc, method_index):
    body = abc.method_body(method_index)
    return disassemble_code(body.code) if body is not None else ()


def _short_name(value):
    return str(value or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]


def _canonical_name(value):
    return str(value or "").replace("::", ".").strip(".")


def _trait_method_map(abc, instance):
    result = {}
    for trait in instance.traits:
        name = abc.multiname_name(trait.name_index)
        if trait.kind in (1, 2, 3) and trait.method_index >= 0:
            result[_short_name(name)] = trait.method_index
        elif trait.kind == 5 and trait.function_index >= 0:
            result[_short_name(name)] = trait.function_index
    return result


def _literal_from_instruction(abc, instruction):
    name = instruction.name
    operand = instruction.operands[0] if instruction.operands else 0
    if name == "pushbyte":
        return int(operand)
    if name == "pushshort":
        value = int(operand)
        return value - 0x10000 if value & 0x8000 else value
    if name == "pushint":
        return abc.ints[operand] if 0 <= operand < len(abc.ints) else 0
    if name == "pushuint":
        return abc.uints[operand] if 0 <= operand < len(abc.uints) else 0
    if name == "pushdouble":
        return abc.doubles[operand] if 0 <= operand < len(abc.doubles) else 0.0
    if name == "pushstring":
        return abc.string(operand)
    if name == "pushtrue":
        return True
    if name == "pushfalse":
        return False
    if name == "pushnull":
        return None
    return None


def _simulate_calls(abc, method_index, trait_methods=None):
    trait_methods = trait_methods or {}
    stack = []
    calls = []
    local_values = {}
    branch_names = {
        "jump", "iftrue", "iffalse", "ifeq", "ifne", "iflt", "ifle", "ifgt", "ifge",
        "ifnlt", "ifnle", "ifngt", "ifnge", "ifstricteq", "ifstrictne", "lookupswitch",
    }

    def pop(default=("unknown",)):
        return stack.pop() if stack else default

    for instruction in disassemble_method(abc, method_index):
        name = instruction.name
        if name == "getlocal_0":
            stack.append(("this",))
        elif name.startswith("getlocal_") and len(name) == len("getlocal_0"):
            stack.append(local_values.get(int(name[-1]), ("local", int(name[-1]))))
        elif name == "getlocal":
            index = int(instruction.operands[0])
            stack.append(local_values.get(index, ("local", index)))
        elif name.startswith("setlocal_") and len(name) == len("setlocal_0"):
            local_values[int(name[-1])] = pop()
        elif name == "setlocal":
            local_values[int(instruction.operands[0])] = pop()
        elif name.startswith("push") and name in {
            "pushbyte", "pushshort", "pushint", "pushuint", "pushdouble", "pushstring",
            "pushtrue", "pushfalse", "pushnull",
        }:
            stack.append(("literal", _literal_from_instruction(abc, instruction)))
        elif name == "pushundefined":
            stack.append(("undefined",))
        elif name == "newfunction":
            stack.append(("method", int(instruction.operands[0]), abc.method_name(instruction.operands[0])))
        elif name in ("getlex", "findproperty", "findpropstrict", "finddef"):
            property_name = _short_name(abc.multiname_name(instruction.operands[0]))
            stack.append(("lex", property_name))
        elif name == "getproperty":
            receiver = pop()
            property_name = _short_name(abc.multiname_name(instruction.operands[0]))
            method = trait_methods.get(property_name)
            if method is not None:
                stack.append(("method", method, property_name))
            else:
                stack.append(("property", receiver, property_name))
        elif name == "dup":
            stack.append(stack[-1] if stack else ("unknown",))
        elif name == "swap":
            if len(stack) >= 2:
                stack[-1], stack[-2] = stack[-2], stack[-1]
        elif name == "pop":
            pop()
        elif name in ("callproperty", "callproplex", "callpropvoid", "callsuper", "callsupervoid"):
            property_name = _short_name(abc.multiname_name(instruction.operands[0]))
            argc = int(instruction.operands[1])
            args = [pop() for _ in range(argc)][::-1]
            receiver = pop()
            calls.append((property_name, tuple(args), receiver, instruction))
            if name in ("callproperty", "callproplex", "callsuper"):
                stack.append(("call-result", property_name))
        elif name in ("call", "construct", "constructsuper", "applytype", "newarray", "newobject"):
            argc = int(instruction.operands[-1]) if instruction.operands else 0
            for _ in range(argc):
                pop()
            pop()
            if name not in ("constructsuper",):
                stack.append(("result", name))
        elif name in branch_names:
            stack.clear()
        elif name in ("returnvoid", "returnvalue", "throw"):
            stack.clear()
    return tuple(calls)


def _stack_literal(value):
    return value[1] if isinstance(value, tuple) and value and value[0] == "literal" else None


def extract_timeline_actions(abc, method_index, trait_methods=None):
    result = []
    for property_name, args, _receiver, _instruction in _simulate_calls(abc, method_index, trait_methods):
        operation = property_name
        if operation in ("stop", "play") and not args:
            result.append(TimelineAction(operation))
        elif operation in ("gotoAndStop", "gotoAndPlay") and args:
            target = _stack_literal(args[0])
            if isinstance(target, (int, str)):
                result.append(TimelineAction(operation, target))
    return tuple(result)


def extract_frame_scripts(module):
    abc = module.abc
    if abc is None:
        return ()
    bindings = []
    for class_index, instance in enumerate(abc.instances):
        class_name = _canonical_name(abc.class_name(class_index))
        trait_methods = _trait_method_map(abc, instance)
        for property_name, args, _receiver, _instruction in _simulate_calls(
            abc, instance.initializer, trait_methods,
        ):
            if property_name != "addFrameScript" or len(args) < 2:
                continue
            for offset in range(0, len(args) - 1, 2):
                frame_value = _stack_literal(args[offset])
                method_value = args[offset + 1]
                if not isinstance(frame_value, int):
                    continue
                if not (isinstance(method_value, tuple) and method_value and method_value[0] == "method"):
                    continue
                method_index = int(method_value[1])
                method_name = str(method_value[2] or abc.method_name(method_index))
                bindings.append(FrameScriptBinding(
                    class_name, max(1, frame_value + 1), method_index, method_name,
                    extract_timeline_actions(abc, method_index, trait_methods), module.name,
                ))
    return tuple(bindings)


def collect_doabc_modules(movie):
    modules = []
    seen = set()

    def scan(tags, source):
        for code, payload in tuple(tags or ()):
            if code == TAG_DO_ABC:
                key = (source, bytes(payload))
                if key in seen:
                    continue
                seen.add(key)
                modules.append(parse_doabc(payload, source))

    scan(getattr(movie, "root_tags", ()), "root")
    for character_id, definition in getattr(movie, "definitions", {}).items():
        if isinstance(definition, ui_browser.SpriteDef):
            scan(getattr(definition, "tags", ()), f"sprite {character_id}")
    return tuple(modules)


def attach_avm2_inventory(movie):
    modules = collect_doabc_modules(movie)
    bindings = []
    for module in modules:
        bindings.extend(extract_frame_scripts(module))
    actions = {}
    bindings_by_class = {}
    for binding in bindings:
        class_name = _canonical_name(binding.class_name)
        bindings_by_class.setdefault(class_name, []).append(binding)
        actions.setdefault(class_name, {}).setdefault(binding.frame, []).extend(binding.actions)
    movie.avm2_modules = modules
    movie.avm2_frame_scripts = tuple(bindings)
    movie.avm2_bindings_by_class = {
        key: tuple(sorted(value, key=lambda item: (item.frame, item.method_index)))
        for key, value in bindings_by_class.items()
    }
    movie.avm2_frame_actions = {
        key: {frame: tuple(value) for frame, value in frames.items()}
        for key, frames in actions.items()
    }
    movie.avm2_parse_errors = tuple(module.error for module in modules if module.error)
    movie.avm2_revision = int(getattr(movie, "avm2_revision", 0)) + 1
    return movie


def parse_swf_movie(raw):
    movie = _BASE_PARSE_SWF(raw)
    return attach_avm2_inventory(movie)


def _class_actions(movie, class_name, frame):
    class_name = _canonical_name(class_name)
    mappings = getattr(movie, "avm2_frame_actions", {}) or {}
    direct = mappings.get(class_name)
    if direct is None:
        short = _short_name(class_name)
        direct = next((value for key, value in mappings.items() if _short_name(key) == short), None)
    return tuple((direct or {}).get(int(frame), ()))


def resolve_action_target(target, frame_count, labels=None):
    labels = labels or {}
    if isinstance(target, str):
        if target in labels:
            target = labels[target]
        else:
            short = target.strip()
            try:
                target = int(short)
            except Exception:
                return None
    if isinstance(target, bool):
        return None
    try:
        value = int(target)
    except Exception:
        return None
    return max(1, min(max(1, int(frame_count)), value))


def execute_timeline_actions(frame, playing, actions, frame_count, labels=None):
    current = max(1, min(max(1, int(frame_count)), int(frame)))
    running = bool(playing)
    jumped = False
    for action in tuple(actions or ()):
        if action.operation == "stop":
            running = False
        elif action.operation == "play":
            running = True
        elif action.operation in ("gotoAndStop", "gotoAndPlay"):
            target = resolve_action_target(action.target, frame_count, labels)
            if target is None:
                continue
            current = target
            running = action.operation == "gotoAndPlay"
            jumped = True
    return current, running, jumped


def timeline_frame_for_path(definition, path, overrides):
    frame = _BASE_TIMELINE_FRAME_FOR_PATH(definition, path, overrides)
    if timeline_core.manual_frame_override(overrides, path) is not None:
        return frame
    movie = getattr(definition, "_ui_timeline_movie", None)
    if movie is None:
        return frame
    class_name = getattr(movie, "symbol_classes", {}).get(getattr(definition, "character_id", None), "")
    if not class_name:
        return frame
    states = getattr(movie, "ui_timeline_states", {}) or {}
    state = states.get(path)
    if state is None:
        return frame
    count = max(1, int(getattr(definition, "frame_count", 1) or 1))
    revision = int(getattr(movie, "avm2_revision", 0))
    visited = set()
    for _ in range(8):
        token = (_canonical_name(class_name), int(frame), revision)
        if state.get("_avm2_script_token") == token or token in visited:
            break
        visited.add(token)
        actions = _class_actions(movie, class_name, frame)
        state["_avm2_script_token"] = token
        if not actions:
            break
        new_frame, playing, jumped = execute_timeline_actions(
            frame, state.get("playing", True), actions, count,
            getattr(definition, "labels", {}),
        )
        state["playing"] = playing
        state["frame"] = new_frame
        frame = new_frame
        if not jumped:
            break
    return max(1, min(count, int(frame)))


def _root_class(movie):
    return str(getattr(movie, "symbol_classes", {}).get(0, "") or "")


def apply_root_frame_script(owner, force=False):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    class_name = _root_class(movie)
    if not class_name:
        return False
    frame = int(owner.frame_var.get())
    revision = int(getattr(movie, "avm2_revision", 0))
    changed = False
    visited = set()
    for _ in range(8):
        token = (_canonical_name(class_name), frame, revision)
        if not force and getattr(movie, "_ui_avm2_root_script_token", None) == token:
            break
        if token in visited:
            break
        visited.add(token)
        movie._ui_avm2_root_script_token = token
        actions = _class_actions(movie, class_name, frame)
        if not actions:
            break
        new_frame, playing, jumped = execute_timeline_actions(
            frame, getattr(owner, "_ui_playback_running", False), actions,
            getattr(movie, "frame_count", 1), getattr(movie, "labels", {}),
        )
        if new_frame != frame:
            timeline_core.set_root_frame(owner, new_frame)
            frame = new_frame
            changed = True
        if playing != bool(getattr(owner, "_ui_playback_running", False)):
            (_BASE_TIMELINE_PLAY if playing else _BASE_TIMELINE_PAUSE)(owner)
            changed = True
        if not jumped:
            break
        force = True
    return changed


def advance(owner, steps=1, force_nested=False):
    result = _BASE_TIMELINE_ADVANCE(owner, steps, force_nested)
    apply_root_frame_script(owner)
    return result


def play(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie._ui_avm2_root_script_token = None
    result = _BASE_TIMELINE_PLAY(owner)
    apply_root_frame_script(owner, force=True)
    return result


def pause(owner):
    return _BASE_TIMELINE_PAUSE(owner)


def _decorate_nodes(movie, nodes):
    result = []
    bindings_by_class = getattr(movie, "avm2_bindings_by_class", {}) or {}
    for node in tuple(nodes or ()):
        metadata = dict(node.metadata)
        children = _decorate_nodes(movie, node.children)
        if node.kind == "MovieClip":
            class_name = node.class_name or metadata.get("symbol_class", "")
            canonical = _canonical_name(class_name)
            bindings = bindings_by_class.get(canonical)
            if bindings is None and canonical:
                short = _short_name(canonical)
                bindings = next((value for key, value in bindings_by_class.items() if _short_name(key) == short), ())
            if bindings:
                frame = int(metadata.get("sprite_frame", 1))
                metadata["avm2_class"] = canonical
                metadata["avm2_frame_scripts"] = tuple(sorted({binding.frame for binding in bindings}))
                current = [binding for binding in bindings if binding.frame == frame]
                metadata["avm2_current_actions"] = tuple(
                    {"operation": action.operation, "target": action.target, "method": binding.method_name}
                    for binding in current for action in binding.actions
                )
        result.append(state_inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, metadata, children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    return _decorate_nodes(movie, _BASE_INSPECT_MOVIE_STATE(movie, frame, max_depth))


def format_state_node(node, resolver=None):
    text = _BASE_FORMAT_STATE_NODE(node, resolver)
    frames = node.metadata.get("avm2_frame_scripts")
    if not frames:
        return text
    lines = ["", "AVM2-Frame-Scripts:"]
    lines.append(f"- Klasse: {node.metadata.get('avm2_class') or '-'}")
    lines.append("- Frames: " + ", ".join(str(frame) for frame in frames))
    actions = node.metadata.get("avm2_current_actions", ())
    if actions:
        lines.append("- Aktionen im aktuellen Frame:")
        for action in actions:
            target = "" if action.get("target") is None else f" {action['target']}"
            lines.append(f"  - {action['operation']}{target} ({action.get('method')})")
    return text + "\n" + "\n".join(lines)


def _operand_text(abc, instruction, index, value):
    schema = _OPCODES.get(instruction.opcode, ("", ()))[1]
    kind = schema[index] if index < len(schema) else ""
    if kind == "mn":
        return f"{value} ({abc.multiname_name(value)})"
    if kind == "string":
        return f"{value} ({abc.string(value)!r})"
    if kind == "method":
        return f"{value} ({abc.method_name(value)})"
    if kind == "class":
        return f"{value} ({abc.class_name(value)})"
    if kind == "int" and 0 <= value < len(abc.ints):
        return f"{value} ({abc.ints[value]})"
    if kind == "uint" and 0 <= value < len(abc.uints):
        return f"{value} ({abc.uints[value]})"
    if kind == "double" and 0 <= value < len(abc.doubles):
        return f"{value} ({abc.doubles[value]!r})"
    if kind == "namespace":
        return f"{value} ({abc.namespace_name(value)})"
    if kind == "switch":
        default, cases = value
        return f"default {default}, cases {list(cases)}"
    return str(value)


def format_disassembly(abc, method_index):
    body = abc.method_body(method_index)
    if body is None:
        return f"{abc.method_name(method_index)} hat keinen Methodenbody."
    method = abc.methods[method_index]
    params = ", ".join(abc.multiname_name(item) for item in method.parameter_types)
    lines = [
        f"Methode {method_index}: {abc.method_name(method_index)}",
        f"Signatur: ({params}) -> {abc.multiname_name(method.return_type)}",
        f"max_stack={body.max_stack}, locals={body.local_count}, scope={body.init_scope_depth}..{body.max_scope_depth}",
        f"Code: {len(body.code)} Bytes, Exceptions: {len(body.exceptions)}", "",
    ]
    for instruction in disassemble_method(abc, method_index):
        operands = ", ".join(
            _operand_text(abc, instruction, index, value)
            for index, value in enumerate(instruction.operands)
        )
        lines.append(f"{instruction.offset:04X}: {instruction.name}" + (f" {operands}" if operands else ""))
    return "\n".join(lines)


def avm2_inventory(movie):
    modules = []
    for module in getattr(movie, "avm2_modules", ()):
        item = {
            "name": module.name, "source": module.source, "flags": module.flags,
            "raw_size": module.raw_size, "error": module.error,
        }
        if module.abc is not None:
            abc = module.abc
            item.update({
                "version": [abc.major_version, abc.minor_version],
                "strings": len(abc.strings) - 1,
                "multinames": len(abc.multinames) - 1,
                "methods": len(abc.methods),
                "classes": [abc.class_name(index) for index in range(len(abc.instances))],
                "scripts": len(abc.scripts),
                "method_bodies": len(abc.method_bodies),
            })
        modules.append(item)
    return {
        "document_class": _root_class(movie),
        "modules": modules,
        "frame_scripts": [
            {
                "module": binding.module_name, "class": binding.class_name,
                "frame": binding.frame, "method": binding.method_name,
                "method_index": binding.method_index,
                "actions": [
                    {"operation": action.operation, "target": action.target}
                    for action in binding.actions
                ],
            }
            for binding in getattr(movie, "avm2_frame_scripts", ())
        ],
    }


class AVM2InspectorWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI AVM2 / Frame Scripts")
        self.geometry("1250x820")
        self.minsize(900, 600)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._items = {}

        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="DoABC-, Klassen-, Methoden- und Frame-Script-Inventar").pack(side="left")
        ttk.Button(toolbar, text="JSON speichern", command=self.save_json).pack(side="right")
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh).pack(side="right", padx=(0, 6))

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(pane)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pane.add(left, weight=0)

        right = ttk.Frame(pane)
        self.details = tk.Text(right, wrap="none", state="disabled")
        self.details.pack(side="left", fill="both", expand=True)
        yscroll = ttk.Scrollbar(right, orient="vertical", command=self.details.yview)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(right, orient="horizontal", command=self.details.xview)
        xscroll.pack(side="bottom", fill="x")
        self.details.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        pane.add(right, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self.refresh()

    def _set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        movie = getattr(self.owner, "_current_movie", None)
        if movie is None:
            self._set_details("Kein UI-Film ausgewählt.")
            self.status_var.set("Keine AVM2-Daten")
            return
        modules = tuple(getattr(movie, "avm2_modules", ()))
        bindings = tuple(getattr(movie, "avm2_frame_scripts", ()))
        root = self.tree.insert("", "end", text=f"Dokumentklasse: {_root_class(movie) or '-'}", open=True)
        self._items[root] = ("summary", movie)
        for module_index, module in enumerate(modules):
            label = f"{module.name} [{module.source}]"
            module_iid = self.tree.insert(root, "end", text=label, open=True)
            self._items[module_iid] = ("module", module)
            if module.abc is None:
                error_iid = self.tree.insert(module_iid, "end", text=f"Fehler: {module.error}")
                self._items[error_iid] = ("text", module.error)
                continue
            abc = module.abc
            classes_iid = self.tree.insert(module_iid, "end", text=f"Klassen ({len(abc.instances)})", open=True)
            for class_index, instance in enumerate(abc.instances):
                class_name = abc.class_name(class_index)
                class_iid = self.tree.insert(classes_iid, "end", text=class_name)
                self._items[class_iid] = ("class", module, class_index)
                class_bindings = [
                    binding for binding in bindings
                    if binding.module_name == module.name and _canonical_name(binding.class_name) == _canonical_name(class_name)
                ]
                for binding in class_bindings:
                    actions = ", ".join(
                        action.operation + (f"({action.target})" if action.target is not None else "")
                        for action in binding.actions
                    ) or "keine direkt ausführbare Timeline-Aktion"
                    iid = self.tree.insert(
                        class_iid, "end",
                        text=f"Frame {binding.frame}: {binding.method_name} → {actions}",
                    )
                    self._items[iid] = ("method", module, binding.method_index)
            methods_iid = self.tree.insert(module_iid, "end", text=f"Methoden ({len(abc.methods)})")
            for method_index in range(len(abc.methods)):
                iid = self.tree.insert(methods_iid, "end", text=f"{method_index}: {abc.method_name(method_index)}")
                self._items[iid] = ("method", module, method_index)
        self.tree.item(root, open=True)
        self.tree.selection_set(root)
        self.on_select()
        errors = sum(1 for module in modules if module.error)
        self.status_var.set(f"{len(modules)} DoABC-Module | {sum(len(m.abc.instances) for m in modules if m.abc)} Klassen | {len(bindings)} Frame-Scripts | {errors} Fehler")

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        item = self._items.get(selection[0])
        if item is None:
            return
        kind = item[0]
        if kind == "summary":
            self._set_details(json.dumps(avm2_inventory(item[1]), ensure_ascii=False, indent=2))
        elif kind == "module":
            module = item[1]
            if module.abc is None:
                self._set_details(module.error)
            else:
                abc = module.abc
                self._set_details(
                    f"Modul: {module.name}\nQuelle: {module.source}\nFlags: 0x{module.flags:08X}\n"
                    f"ABC-Version: {abc.major_version}.{abc.minor_version}\nGröße: {module.raw_size} Bytes\n\n"
                    f"Strings: {len(abc.strings)-1}\nNamespaces: {len(abc.namespaces)-1}\n"
                    f"Multinames: {len(abc.multinames)-1}\nMethoden: {len(abc.methods)}\n"
                    f"Klassen: {len(abc.instances)}\nScripts: {len(abc.scripts)}\n"
                    f"Methodenbodies: {len(abc.method_bodies)}\nTrailing Bytes: {len(abc.trailing_bytes)}"
                )
        elif kind == "class":
            module, class_index = item[1], item[2]
            abc = module.abc
            instance = abc.instances[class_index]
            methods = _trait_method_map(abc, instance)
            lines = [
                f"Klasse: {abc.class_name(class_index)}",
                f"Basisklasse: {abc.multiname_name(instance.super_name_index)}",
                f"Instance-Initializer: {instance.initializer} ({abc.method_name(instance.initializer)})",
                f"Traits: {len(instance.traits)}", "",
            ]
            lines.extend(f"- {name}: Methode {index} ({abc.method_name(index)})" for name, index in sorted(methods.items()))
            self._set_details("\n".join(lines))
        elif kind == "method":
            module, method_index = item[1], item[2]
            self._set_details(format_disassembly(module.abc, method_index))
        elif kind == "text":
            self._set_details(str(item[1]))

    def save_json(self):
        movie = getattr(self.owner, "_current_movie", None)
        if movie is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="AVM2-Inventar speichern", defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(avm2_inventory(movie), handle, ensure_ascii=False, indent=2)

    def close(self):
        self.owner._avm2_inspector = None
        self.destroy()


def show_avm2_inspector(owner):
    window = getattr(owner, "_avm2_inspector", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._avm2_inspector = AVM2InspectorWindow(owner)
    return owner._avm2_inspector


def browser_init(owner, *args, **kwargs):
    owner._avm2_inspector = None
    _BASE_BROWSER_INIT(owner, *args, **kwargs)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Button(bar, text="AVM2 / Frame Scripts", command=lambda: show_avm2_inspector(owner)).pack(side="left")
    ttk.Label(bar, text="F9 öffnet DoABC-, Klassen- und Methoden-Inventar").pack(side="left", padx=(10, 0))
    owner.bind("<F9>", lambda _event: show_avm2_inspector(owner))


def browser_tree_select(owner, event=None):
    result = _BASE_BROWSER_TREE_SELECT(owner, event)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None and not hasattr(movie, "avm2_modules"):
        attach_avm2_inventory(movie)
    window = getattr(owner, "_avm2_inspector", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass
    return result


def browser_render(owner):
    apply_root_frame_script(owner)
    return _BASE_BROWSER_RENDER(owner)


def browser_format_info(owner, stats):
    text = _BASE_BROWSER_FORMAT_INFO(owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    modules = tuple(getattr(movie, "avm2_modules", ()))
    if not modules:
        return text + "\n\nAVM2:\n- Keine DoABC-Module"
    classes = sum(len(module.abc.instances) for module in modules if module.abc is not None)
    methods = sum(len(module.abc.methods) for module in modules if module.abc is not None)
    bindings = tuple(getattr(movie, "avm2_frame_scripts", ()))
    safe_actions = sum(len(binding.actions) for binding in bindings)
    errors = sum(1 for module in modules if module.error)
    return text + "\n\nAVM2:\n" + (
        f"- DoABC-Module: {len(modules)}\n"
        f"- Dokumentklasse: {_root_class(movie) or '-'}\n"
        f"- Klassen: {classes}\n"
        f"- Methoden: {methods}\n"
        f"- Frame-Scripts: {len(bindings)}\n"
        f"- Sichere Timeline-Aktionen: {safe_actions}\n"
        f"- Parserfehler: {errors}"
    )


def browser_close(owner):
    window = getattr(owner, "_avm2_inspector", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE_BROWSER_CLOSE(owner)


def install():
    global _INSTALLED, _BASE_PARSE_SWF, _BASE_INSPECT_MOVIE_STATE, _BASE_FORMAT_STATE_NODE
    global _BASE_BROWSER_INIT, _BASE_BROWSER_TREE_SELECT, _BASE_BROWSER_FORMAT_INFO
    global _BASE_BROWSER_CLOSE, _BASE_BROWSER_RENDER, _BASE_TIMELINE_FRAME_FOR_PATH
    global _BASE_TIMELINE_ADVANCE, _BASE_TIMELINE_PLAY, _BASE_TIMELINE_PAUSE
    if _INSTALLED:
        return
    _INSTALLED = True

    _BASE_PARSE_SWF = ui_browser.parse_swf_movie
    _BASE_INSPECT_MOVIE_STATE = state_inspector.inspect_movie_state
    _BASE_FORMAT_STATE_NODE = state_inspector.format_state_node
    _BASE_BROWSER_INIT = ui_browser.UIBrowser.__init__
    _BASE_BROWSER_TREE_SELECT = ui_browser.UIBrowser._on_tree_select
    _BASE_BROWSER_FORMAT_INFO = ui_browser.UIBrowser._format_info
    _BASE_BROWSER_CLOSE = ui_browser.UIBrowser.close
    _BASE_BROWSER_RENDER = ui_browser.UIBrowser._render
    _BASE_TIMELINE_FRAME_FOR_PATH = timeline_core.timeline_frame_for_path
    _BASE_TIMELINE_ADVANCE = timeline_browser.advance
    _BASE_TIMELINE_PLAY = timeline_browser.play
    _BASE_TIMELINE_PAUSE = timeline_browser.pause

    ui_browser.TAG_DO_ABC = TAG_DO_ABC
    ui_browser.parse_swf_movie = parse_swf_movie
    timeline_core.timeline_frame_for_path = timeline_frame_for_path
    try:
        import ui_browser_state_override_patch as override_patch
        override_patch.sprite_frame_for_path = timeline_frame_for_path
    except Exception:
        pass

    timeline_browser.advance = advance
    timeline_browser.play = play
    timeline_browser.pause = pause
    ui_browser.UIBrowser.play_ui_timelines = play
    ui_browser.UIBrowser.pause_ui_timelines = pause

    state_inspector.inspect_movie_state = inspect_movie_state
    state_inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_tree_select
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser._format_info = browser_format_info
    ui_browser.UIBrowser.close = browser_close
    ui_browser.UIBrowser.show_avm2_inspector = show_avm2_inspector

    ui_browser.parse_abc = parse_abc
    ui_browser.parse_doabc = parse_doabc
    ui_browser.disassemble_avm2_method = disassemble_method
    ui_browser.extract_avm2_frame_scripts = extract_frame_scripts
    ui_browser.execute_avm2_timeline_actions = execute_timeline_actions
    ui_browser.avm2_inventory = avm2_inventory
