"""
ontology_to_json.py  -  ontology + SHACL + SKOS  ->  one JSON file per domain, in 11 small steps.
The output file of one step is the input file of the next step.

    step 1  find the domains                     -> step1_domains.json
    step 2  find the classes of every domain     -> step2_classes.json
    step 3  find the attributes of every class   -> step3_attributes.json
    step 4  decide the kind of every attribute   -> step4_kinds.json
    step 5  give an "id" to the classes without sh:order 1 -> step5_ids.json
    step 6  number the attributes (intId)        -> step6_numbers.json
    step 7  add the multiplicity                  -> step7_multiplicity.json
    step 8  real data type, unit and range        -> step8_details.json
    step 9  ordered and formatNote                -> step9_order_notes.json
    step 10 info, label, key, exp, subsetName, ontology, sameKeyAs, sub-package, union -> step10_texts.json
    step 11 fill in the value lists              -> kinds_<DOMAIN>.json  (the final files)

THE RULES
  Kind of an attribute. The SHACL decides, in this order:
      1. it has sh:node  AND  nodeKind = BlankNodeOrIRI      -> composition   (sh:class is ignored)
      2. it has sh:in                                         -> enumType
      3. every other link                                     -> reference
      If the SHACL has no rule at all, the ontology decides (list name -> enumType,
      plain type -> dataType). If nobody can decide, the attribute is marked TODO.
  id:     every class that HAS attributes gets the attribute "id" with intId 1, EXCEPT a class
          that has an attribute with sh:order 1 (that attribute is number 1). References do not matter.
  intId:  the sh:order of the attribute. If there is none, the next free number.
  Value lists: every domain file has a full copy of every list it uses.
          The values and their order come from the SHACL (sh:in).
          The name of a value comes from the SKOS files: the hidden label that starts with
          CCSTMS_ , without "CCSTMS_" and without the index at the end (CCSTMS_CD_80mm_1 -> CD_80mm).
          If there is no such label, the code at the end of the address is used (80).

Put in one folder: ontology.ttl, the *-shapes_*.ttl files, the SKOS files, this program.
(Change SHACL_FOLDER or SKOS_FOLDER below if they are somewhere else.)

Run:   python ontology_to_json.py              all 11 steps, all domains
       python ontology_to_json.py 4            start at step 4 (needs step3_attributes.json), run 4 to 11
       python ontology_to_json.py infra        all 11 steps, but write only kinds_INFRA.json
       python ontology_to_json.py eng          all 11 steps, but write only kinds_ENG.json
       python ontology_to_json.py 7 eng        start at step 7, write only kinds_ENG.json
       python ontology_to_json.py infra eng    write the final files of INFRA and ENG only
       (the number is the first step, the words are domain names; capital letters do not matter)
       The steps 1 to 10 always work on all domains, because some rules look at INFRA
       (ENG does not repeat what INFRA has, sameKeyAs, id). Only the final files are chosen.
"""
import glob
import json
import os
import re
import sys

from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, BNode
from rdflib.collection import Collection

# ------------------------------------------------------------------ settings
ONTOLOGY_FILE = "ontology.ttl"
SHACL_FOLDER = "SHACL_shape"
SKOS_FOLDER = "skos"

ERA = "http://data.europa.eu/949/"
XSD = "http://www.w3.org/2001/XMLSchema#"
SH = Namespace("http://www.w3.org/ns/shacl#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

DOMAIN_STICKER = URIRef(ERA + "ccsView")                 # says which domain a class or attribute belongs to
LIST_NAME_PROPERTY = URIRef(ERA + "inSkosConceptScheme")  # the name of a value list
LABEL_START = "CCSTMS_"

KINDS = ("reference", "composition", "enumType", "dataType")

PLAIN_TYPES = [
    XSD + "string", "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
    XSD + "double", XSD + "decimal", XSD + "boolean", XSD + "integer", XSD + "int",
    XSD + "nonNegativeInteger", XSD + "unsignedInt", XSD + "positiveInteger",
    XSD + "dateTime", XSD + "dateTimeStamp", XSD + "date", XSD + "base64Binary",
    XSD + "unsignedLong", XSD + "unsignedShort", XSD + "unsignedByte",
    XSD + "long", XSD + "short", XSD + "byte", XSD + "float",
]

# Data types. Name in the JSON  ->  xsd type (the mapping we were given).
JSON_TYPE_TO_XSD = {
    "uint64":    "xsd:unsignedLong",
    "uint32":    "xsd:unsignedInt",
    "uint16":    "xsd:unsignedShort",
    "uint8":     "xsd:unsignedByte",
    "int64":     "xsd:long",
    "int32":     "xsd:int",
    "int16":     "xsd:short",
    "int8":      "xsd:byte",
    "boolean":   "xsd:boolean",
    "bytes":     "xsd:base64Binary",
    "timestamp": "xsd:dateTimeStamp",
    "double":    "xsd:double",
    "string":    "xsd:string",
    "dateTime":  "xsd:dateTime",
    "float":     "xsd:float",
    "decimal":   "xsd:decimal",
    "date":      "xsd:date",
}

# If two names point to the same xsd type, this says which name we write.
# Now every xsd type has only one name, so nothing is needed here.
PREFERRED_JSON_TYPE = {}

# The program needs the other direction: xsd type in the SHACL (sh:datatype, last part)  ->  name in the JSON
DATA_TYPE_NAMES = {}
for json_name in JSON_TYPE_TO_XSD:
    xsd_name = JSON_TYPE_TO_XSD[json_name]
    if xsd_name in PREFERRED_JSON_TYPE and PREFERRED_JSON_TYPE[xsd_name] != json_name:
        continue
    DATA_TYPE_NAMES[xsd_name.split(":")[-1]] = json_name

# Units. Symbol in the JSON  ->  unit in the ontology (era:unitOfMeasure, last part of the address).
SYMBOL_TO_UNIT = {
    "m":       "unit:M",
    "mm":      "unit:MilliM",
    "km/h":    "unit:KiloM-PER-HR",
    "m/s":     "unit:M-PER-SEC",
    "minute":  "unit:MIN",
    "m/s2":    "unit:M-PER-SEC2",
    "cm":      "unit:CentiM",
    "m2":      "unit:M2",
    "m3":      "unit:M3",
    "kg":      "unit:KiloGM",
    "kN":      "unit:KiloN",
    "N":       "unit:N",
    "s":       "unit:SEC",
    "V":       "unit:V",
    "W":       "unit:W",
    "A":       "unit:A",
    "Ohm":     "unit:OHM",
    "K":       "unit:K",
    "Hz":      "unit:HZ",
    "degree":  "unit:DEG",
    "rad":     "unit:RAD",
    "W/m2":    "unit:W-PER-M2",
    "permill": "unit:MilliM-PER-M",
    "Pa":      "unit:PA",
    "percent": "unit:PERCENT",
    "1/m":     "unit:PER-M",
    "bar":     "unit:BAR",
    "ms":      "unit:MilliSEC",
    "day":     "unit:DAY",
    "km":      "unit:KiloM",
}

# The program needs the other direction: unit in the ontology  ->  symbol in the JSON
UNIT_SYMBOLS = {}
for symbol in SYMBOL_TO_UNIT:
    unit_name = SYMBOL_TO_UNIT[symbol]
    if unit_name.startswith("unit:"):
        unit_name = unit_name[len("unit:"):]
    UNIT_SYMBOLS[unit_name] = symbol

ID_INFO = "Identity of the object; used for referencing"

STEP_FILES = {
    1: "step1_domains.json",
    2: "step2_classes.json",
    3: "step3_attributes.json",
    4: "step4_kinds.json",
    5: "step5_ids.json",
    6: "step6_numbers.json",
    7: "step7_multiplicity.json",
    8: "step8_details.json",
    9: "step9_order_notes.json",
    10: "step10_texts.json",
}


# ------------------------------------------------------------------ small helpers
def short_name(address):
    """http://data.europa.eu/949/BufferStop -> BufferStop"""
    return str(address).replace(ERA, "")


def name_without_prefix(name):
    """infra.TopoArea -> TopoArea"""
    return name.split(".")[-1]


def save_json(file_name, data):
    with open(file_name, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=1, ensure_ascii=False)
    print("   -> written:", file_name)


def load_json(file_name):
    if not os.path.exists(file_name):
        print("The file", file_name, "is missing. Run the earlier steps first.")
        sys.exit(1)
    with open(file_name, encoding="utf-8") as file:
        return json.load(file)


def get_int_id(attribute):
    return attribute["intId"]


# ================================================================== Ontology
class Ontology:
    """The catalogue (ontology.ttl): which domains, classes and attributes exist."""

    def __init__(self, file_name):
        self.graph = Graph()
        self.graph.parse(file_name, format="turtle")
        # all attributes (data properties and link properties), sorted by address
        attribute_addresses = set(self.graph.subjects(RDF.type, OWL.DatatypeProperty))
        attribute_addresses.update(self.graph.subjects(RDF.type, OWL.ObjectProperty))
        self.all_attributes = sorted(attribute_addresses, key=str)

    def get_stickers(self, name):
        """The domains (stickers) of a class or attribute, as a set of texts."""
        stickers = set()
        for sticker in self.graph.objects(URIRef(ERA + name), DOMAIN_STICKER):
            stickers.add(str(sticker))
        return stickers

    def find_domain_names(self):
        """All domain names. INFRA comes first."""
        found = set()
        for sticker in self.graph.objects(None, DOMAIN_STICKER):
            found.add(str(sticker))
        domain_names = []
        if "INFRA" in found:
            domain_names.append("INFRA")
        for name in sorted(found):
            if name != "INFRA":
                domain_names.append(name)
        return domain_names

    def find_class_names(self, domain_name):
        """The names of all classes that carry the sticker of this domain."""
        class_addresses = []
        for address in self.graph.subjects(RDF.type, OWL.Class):
            if isinstance(address, URIRef):
                if domain_name in self.get_stickers(short_name(address)):
                    class_addresses.append(address)
        class_addresses.sort(key=str)
        class_names = []
        for address in class_addresses:
            class_names.append(short_name(address))
        return class_names

    def find_owner_classes(self, attribute_address):
        """The classes that own an attribute. Sometimes there are several (owl:unionOf)."""
        owners = []
        for owner in self.graph.objects(attribute_address, RDFS.domain):
            if isinstance(owner, BNode):
                union = self.graph.value(owner, OWL.unionOf)
                if union is not None:
                    for member in Collection(self.graph, union):
                        owners.append(short_name(member))
            else:
                owners.append(short_name(owner))
        return owners

    def find_attributes_by_class(self, domain_name):
        """{class name: [attribute names]} for the attributes with the sticker of this domain."""
        attributes_by_class = {}
        for attribute_address in self.all_attributes:
            attribute_name = short_name(attribute_address)
            if domain_name not in self.get_stickers(attribute_name):
                continue
            for class_name in self.find_owner_classes(attribute_address):
                if class_name not in attributes_by_class:
                    attributes_by_class[class_name] = []
                attributes_by_class[class_name].append(attribute_name)
        return attributes_by_class

    def find_infra_attributes(self):
        """{class name: set of attribute names} that INFRA has. Other domains do not repeat them."""
        infra_attributes = {}
        for attribute_address in self.all_attributes:
            attribute_name = short_name(attribute_address)
            if "INFRA" not in self.get_stickers(attribute_name):
                continue
            for class_name in self.find_owner_classes(attribute_address):
                if "INFRA" not in self.get_stickers(class_name):
                    continue
                if class_name not in infra_attributes:
                    infra_attributes[class_name] = set()
                infra_attributes[class_name].add(attribute_name)
        return infra_attributes

    def has_subclass(self, class_name):
        """True if another class inherits from this class."""
        for child in self.graph.subjects(RDFS.subClassOf, URIRef(ERA + class_name)):
            if child != URIRef(ERA + class_name):
                return True
        return False

    def is_link(self, attribute_name):
        """True if the attribute points to another class (or to a list)."""
        return (URIRef(ERA + attribute_name), RDF.type, OWL.ObjectProperty) in self.graph

    def get_list_name(self, attribute_name):
        """The name of the value list from the ontology, or None."""
        address = self.graph.value(URIRef(ERA + attribute_name), LIST_NAME_PROPERTY)
        if address is None:
            return None
        return str(address).split("/")[-1]

    def has_plain_type(self, attribute_name):
        """True if the attribute holds a plain value (text, number, date ...)."""
        range_node = self.graph.value(URIRef(ERA + attribute_name), RDFS.range)
        if range_node is None:
            return False
        if isinstance(range_node, BNode):
            base_type = self.graph.value(range_node, OWL.onDatatype)
            if base_type is None:
                return False
            return str(base_type) in PLAIN_TYPES
        return str(range_node) in PLAIN_TYPES

    def get_unit_name(self, attribute_name):
        """The unit of the attribute from the ontology (last part of the address), or None."""
        address = self.graph.value(URIRef(ERA + attribute_name), URIRef(ERA + "unitOfMeasure"))
        if address is None:
            return None
        return str(address).split("/")[-1]

    def get_ordered(self, attribute_name):
        """"byKey" or "byIndex" from era:ordered in the ontology, or None."""
        value = self.graph.value(URIRef(ERA + attribute_name), URIRef(ERA + "ordered"))
        if value is None:
            return None
        return str(value)

    def get_format_note(self, attribute_name):
        """The text of era:formatNote in the ontology, or None."""
        value = self.graph.value(URIRef(ERA + attribute_name), URIRef(ERA + "formatNote"))
        if value is None:
            return None
        return str(value)

    def get_english_text(self, address, property_address):
        """One text (rdfs:comment, rdfs:label ...) of a thing. The English one is preferred."""
        found = list(self.graph.objects(address, property_address))
        for text in found:
            if getattr(text, "language", None) == "en":
                return str(text)
        if len(found) > 0:
            return str(found[0])
        return None

    def get_comment(self, name):
        return self.get_english_text(URIRef(ERA + name), RDFS.comment)

    def get_label(self, name):
        return self.get_english_text(URIRef(ERA + name), RDFS.label)

    def get_key(self, attribute_name):
        """era:key in the ontology ("local"), or None."""
        value = self.graph.value(URIRef(ERA + attribute_name), URIRef(ERA + "key"))
        if value is None:
            return None
        return str(value)

    def get_exp(self, attribute_name):
        """era:exp as a whole number (for example -3), or None."""
        value = self.graph.value(URIRef(ERA + attribute_name), URIRef(ERA + "exp"))
        if value is None:
            return None
        return int(value)

    def get_subset_name(self, attribute_name):
        """era:unisigSubsetName, or None."""
        values = []
        for value in self.graph.objects(URIRef(ERA + attribute_name), URIRef(ERA + "unisigSubsetName")):
            values.append(str(value))
        if len(values) == 0:
            return None
        values.sort()
        if len(values) == 1:
            return values[0]
        return values                 # more than one value: all of them are given (speed: V_STATIC, V_TRAIN)

    def get_super_properties(self, attribute_name):
        """rdfs:subPropertyOf parents. Everything that is in the ontology is given."""
        parents = []
        for parent in self.graph.objects(URIRef(ERA + attribute_name), RDFS.subPropertyOf):
            if isinstance(parent, URIRef):
                parents.append(str(parent))
        return sorted(parents)

    def get_property_types(self, attribute_name):
        """Extra types of the attribute, like owl:IrreflexiveProperty (not ObjectProperty / DatatypeProperty / FunctionalProperty)."""
        ignore = [OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property, OWL.FunctionalProperty]
        types = []
        for type_address in self.graph.objects(URIRef(ERA + attribute_name), RDF.type):
            if type_address not in ignore:
                types.append(str(type_address))
        return sorted(types)

    def get_super_classes(self, class_name):
        """rdfs:subClassOf parents that are real named classes (not anonymous restrictions)."""
        parents = []
        for parent in self.graph.objects(URIRef(ERA + class_name), RDFS.subClassOf):
            if isinstance(parent, URIRef):
                parents.append(str(parent))
        return sorted(parents)

    def add_domain_prefix(self, target_name, domain_name):
        """A class of ANOTHER domain gets a prefix: TopoArea -> infra.TopoArea"""
        stickers = self.get_stickers(target_name)
        if domain_name in stickers or len(stickers) == 0:
            return target_name
        if "INFRA" in stickers:
            return "infra." + target_name
        return sorted(stickers)[0].lower() + "." + target_name


# ================================================================== SHACL
class ShaclRules:
    """The SHACL files. Tell us the kind of an attribute, its sh:order and the values of a list."""

    def __init__(self, folder):
        self.files = []                  # [(file name, graph), ...]
        for path in sorted(glob.glob(os.path.join(folder, "*-shapes_*.ttl"))):
            graph = Graph()
            graph.parse(path, format="turtle")
            self.files.append((os.path.basename(path).lower(), graph))
        self.unusual_rules = []          # unusual rules we noticed, to show them on the screen

    def get_graphs(self, domain_name):
        """All SHACL graphs. The files of this domain come first."""
        own_graphs = []
        other_graphs = []
        for file_name, graph in self.files:
            if file_name.startswith(domain_name.lower() + "-"):
                own_graphs.append(graph)
            else:
                other_graphs.append(graph)
        return own_graphs + other_graphs

    def find_shape(self, domain_name, class_name, attribute_name):
        """
        Finds the SHACL block of one attribute. Its name ends with  <Class>-<attribute>.
        Returns (graph, attribute_shape, rule_shape) or (None, None, None).
          attribute_shape = the block of the attribute (it has sh:order)
          rule_shape      = the block with the rules (sh:class, sh:node, sh:in ...).
                            Usually the same block. For a list of objects the rules for ONE
                            element are in the small block '...-items'.
        """
        wanted_end = "#" + class_name + "-" + attribute_name
        for graph in self.get_graphs(domain_name):
            for attribute_shape in graph.subjects(SH.path, URIRef(ERA + attribute_name)):
                if not str(attribute_shape).endswith(wanted_end):
                    continue
                rule_shape = attribute_shape
                node_address = graph.value(attribute_shape, SH.node)
                if node_address is not None and str(node_address).endswith("-items"):
                    inner_shape = graph.value(node_address, SH.property)
                    if inner_shape is not None:
                        rule_shape = inner_shape
                return graph, attribute_shape, rule_shape
        return None, None, None

    def get_class_name_from_shape(self, shape_address):
        """infra-sh:NetLinearReferenceShape -> NetLinearReference"""
        name = str(shape_address).split("#")[-1]
        if name.endswith("Shape"):
            name = name[:-len("Shape")]
        if "-" in name:
            name = name.replace("-", ".", 1)         # infra-PlatformEdge -> infra.PlatformEdge
        return name

    def get_list_name_from_message(self, graph, rule_shape):
        """
        The message says: "Value must be one of the CCSTMS-scoped SleepersType concepts."
        The word between 'CCSTMS-scoped' and 'concepts' is the list name.
        (The message can come in several languages. Only the English one has these words.)
        """
        for message in graph.objects(rule_shape, SH.message):
            found = re.search(r"CCSTMS-scoped\s+(\S+)\s+concepts", str(message))
            if found is not None:
                return found.group(1)
        return None

    def get_link(self, domain_name, class_name, attribute_name):
        """
        Returns (kind, name) or None if the SHACL has no usable rule.
            sh:node and nodeKind BlankNodeOrIRI  -> ("composition", class name)
            sh:in                                -> ("enumType", list name or None)
            everything else with a class         -> ("reference", class name)
        """
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if rule_shape is None:
            return None

        where = class_name + "." + attribute_name
        sh_node = graph.value(rule_shape, SH.node)
        sh_class = graph.value(rule_shape, SH["class"])
        sh_in = graph.value(rule_shape, SH["in"])
        node_kind = graph.value(rule_shape, SH.nodeKind)
        node_kind_is_blank_or_iri = (node_kind == SH.BlankNodeOrIRI)

        # 1. composition: the object is described inside
        if sh_node is not None and node_kind_is_blank_or_iri:
            if sh_class is not None:
                self.add_unusual_rule(where, "has sh:class and sh:node: composition wins")
            return "composition", self.get_class_name_from_shape(sh_node)

        # 2. enumType: one value of a fixed list
        if sh_in is not None:
            return "enumType", self.get_list_name_from_message(graph, rule_shape)

        # 3. everything else is a reference
        if sh_node is not None:
            self.add_unusual_rule(where, "has sh:node but nodeKind is not BlankNodeOrIRI: made a reference")
        if node_kind_is_blank_or_iri and sh_node is None:
            self.add_unusual_rule(where, "nodeKind is BlankNodeOrIRI but no sh:node: made a reference")
        if sh_class is not None:
            return "reference", short_name(sh_class)
        if sh_node is not None:
            return "reference", self.get_class_name_from_shape(sh_node)
        return None

    def add_unusual_rule(self, where, text):
        if (where, text) not in self.unusual_rules:
            self.unusual_rules.append((where, text))

    def get_sh_order(self, domain_name, class_name, attribute_name):
        """The sh:order of the attribute as a number, or None if there is none."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        order = graph.value(attribute_shape, SH.order)
        if order is None:
            return None
        return int(order)

    def get_value_addresses(self, domain_name, class_name, attribute_name):
        """The addresses of the allowed values of a list, in the SHACL order. None if there is no sh:in."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if rule_shape is None:
            return None
        sh_in = graph.value(rule_shape, SH["in"])
        if sh_in is None:
            return None
        addresses = []
        for member in Collection(graph, sh_in):
            addresses.append(str(member))
        return addresses


    def get_data_type(self, domain_name, class_name, attribute_name):
        """The xsd type of a plain value from sh:datatype, e.g. "unsignedInt". None if there is none."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        data_type = graph.value(attribute_shape, SH.datatype)
        if data_type is None:
            return None
        return str(data_type).split("#")[-1]

    def get_range(self, domain_name, class_name, attribute_name):
        """The allowed range as text "min..max" from sh:minInclusive and sh:maxInclusive. None if not both."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        smallest = graph.value(attribute_shape, SH.minInclusive)
        biggest = graph.value(attribute_shape, SH.maxInclusive)
        if smallest is None or biggest is None:
            return None
        return str(smallest) + ".." + str(biggest)

    def is_ordered_by_index(self, domain_name, class_name, attribute_name):
        """
        True if the SHACL has the rule <Class>-<attribute>-listWellFormed.
        Its message says: "... is ordered byIndex and must therefore be a well-formed rdf:List".
        """
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if graph is None:
            return False
        wanted_end = class_name + "-" + attribute_name + "-listWellFormed"
        for rule in graph.subjects(RDF.type, SH.SPARQLConstraint):
            if str(rule).endswith(wanted_end):
                return True
        return False

    def get_description(self, domain_name, class_name, attribute_name):
        """sh:description of the attribute rule card, or None."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        return self.pick_text(graph, attribute_shape)

    def get_class_description(self, domain_name, class_name):
        """sh:description of the class form (NodeShape with sh:targetClass), or None."""
        for graph in self.get_graphs(domain_name):
            for form in graph.subjects(SH.targetClass, URIRef(ERA + class_name)):
                text = self.pick_text(graph, form)
                if text is not None:
                    return text
        return None

    def pick_text(self, graph, shape):
        found = list(graph.objects(shape, SH.description))
        for text in found:
            if getattr(text, "language", None) in (None, "en"):
                return str(text)
        if len(found) > 0:
            return str(found[0])
        return None

    def find_class_forms(self, domain_name, class_name):
        """All class forms (NodeShape with sh:targetClass) of a class: pairs (graph, form)."""
        forms = []
        for graph in self.get_graphs(domain_name):
            for form in graph.subjects(SH.targetClass, URIRef(ERA + class_name)):
                forms.append((graph, form))
        return forms

    def get_sub_package(self, domain_name, class_name):
        """The comment 'sub-package: geometry' on the class form (in the shapes file of this domain) gives "geometry", or None."""
        # Only the shapes file of THIS domain counts (not the other domains, not the dataprep files).
        own_file_start = domain_name.lower() + "-shapes"
        for file_name, graph in self.files:
            if not file_name.startswith(own_file_start):
                continue
            for form in graph.subjects(SH.targetClass, URIRef(ERA + class_name)):
                for comment in graph.objects(form, RDFS.comment):
                    found = re.search(r"sub-package:\s*(\S+)", str(comment))
                    if found is not None:
                        return found.group(1)
        return None

    def is_union(self, domain_name, class_name):
        """True if the class form has sh:xone: exactly one of the attributes must be present."""
        for graph, form in self.find_class_forms(domain_name, class_name):
            if graph.value(form, SH.xone) is not None:
                return True
        return False

    def get_pattern(self, domain_name, class_name, attribute_name):
        """sh:pattern of the attribute rule card without the start ^ and the end $, or None."""
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        pattern = graph.value(attribute_shape, SH.pattern)
        if pattern is None:
            pattern = graph.value(rule_shape, SH.pattern)
        if pattern is None:
            return None
        text = str(pattern)
        if text.startswith("^"):
            text = text[1:]
        if text.endswith("$"):
            text = text[:-1]
        return text

    def get_item_bounds(self, graph, class_name, attribute_name):
        """
        For a list (rdf:List) the bounds of the ITEMS are not in sh:minCount / sh:maxCount.
        They are in a small SPARQL rule  <Class>-<attribute>-listItemCount.
        Its HAVING line says  COUNT(?item) < 1  (at least 1)  and  COUNT(?item) > 8  (at most 8).
        Returns (min, max) or None if there is no such rule.
        """
        wanted_end = class_name + "-" + attribute_name + "-listItemCount"
        for rule in graph.subjects(RDF.type, SH.SPARQLConstraint):
            if not str(rule).endswith(wanted_end):
                continue
            text = str(graph.value(rule, SH.select))
            minimum = 0
            maximum = None
            found_min = re.search(r"COUNT\(\?item\)\s*<\s*(\d+)", text)
            found_max = re.search(r"COUNT\(\?item\)\s*>\s*(\d+)", text)
            if found_min is not None:
                minimum = int(found_min.group(1))
            if found_max is not None:
                maximum = int(found_max.group(1))
            return minimum, maximum
        return None

    def get_multiplicity(self, domain_name, class_name, attribute_name):
        """
        The multiplicity as text, e.g. "1..1", "0..1", "1..8", "0..*". None if the SHACL has no rule.
        List attributes (sh:node ...-items): the bounds of the items are used.
        Otherwise sh:minCount (missing = 0) and sh:maxCount (missing = *).
        """
        graph, attribute_shape, rule_shape = self.find_shape(domain_name, class_name, attribute_name)
        if attribute_shape is None:
            return None
        node_address = graph.value(attribute_shape, SH.node)
        is_list = (node_address is not None and str(node_address).endswith("-items"))
        if is_list:
            bounds = self.get_item_bounds(graph, class_name, attribute_name)
            if bounds is not None:
                minimum, maximum = bounds
                return self.write_bounds(minimum, maximum)
            return "0..*"            # a list without a bound on its items
        min_count = graph.value(attribute_shape, SH.minCount)
        max_count = graph.value(attribute_shape, SH.maxCount)
        minimum = 0
        maximum = None
        if min_count is not None:
            minimum = int(min_count)
        if max_count is not None:
            maximum = int(max_count)
        return self.write_bounds(minimum, maximum)

    def write_bounds(self, minimum, maximum):
        if maximum is None:
            return str(minimum) + "..*"
        return str(minimum) + ".." + str(maximum)


# ================================================================== SKOS
class SkosLabels:
    """The SKOS files. For every value of a list we read the hidden label that starts with CCSTMS_."""

    def __init__(self, folder):
        self.labels = {}                 # address of a value -> its label, e.g. CCSTMS_CD_80mm_1
        self.file_count = 0
        ontology_name = os.path.basename(ONTOLOGY_FILE).lower()
        paths = sorted(glob.glob(os.path.join(folder, "**", "*.ttl"), recursive=True))
        for path in paths:
            file_name = os.path.basename(path).lower()
            if file_name == ontology_name or "-shapes_" in file_name:
                continue
            graph = Graph()
            try:
                graph.parse(path, format="turtle")
            except Exception as error:
                print("   WARNING: cannot read", file_name, "-", error)
                continue
            labels_in_file = 0
            for value_address, label in graph.subject_objects(SKOS.hiddenLabel):
                if (value_address, SKOS.inScheme, None) not in graph:
                    continue             # this is the label of the list itself, not of a value
                if str(label).startswith(LABEL_START):
                    self.labels[str(value_address)] = str(label)
                    labels_in_file = labels_in_file + 1
            if labels_in_file > 0:
                self.file_count = self.file_count + 1

    def get_value_name(self, value_address):
        """
        Returns (name, found). CCSTMS_CD_80mm_1 -> CD_80mm
        If there is no label, the code at the end of the address is used and found is False.
        """
        label = self.labels.get(value_address)
        if label is None:
            return value_address.split("/")[-1], False
        name = label[len(LABEL_START):]
        name = re.sub(r"_\d+(@[a-z]+)?$", "", name)   # remove the index at the end (and a stray @en after it)
        return name, True

    def get_value_index(self, value_address):
        """
        The number at the end of the SKOS label: CCSTMS_CD_80mm_1 -> 1 (a stray @en after it is ignored).
        Returns None if the value has no label or the label has no number at the end.
        """
        label = self.labels.get(value_address)
        if label is None:
            return None
        found = re.search(r"_(\d+)(@[a-z]+)?$", label)
        if found is None:
            return None
        return int(found.group(1))


# ================================================================== the 7 steps
def step1_find_domains(ontology):
    domain_names = ontology.find_domain_names()
    print("   domains:", ", ".join(domain_names))
    return {"domains": domain_names}


def step2_find_classes(ontology, data):
    domains = []
    for domain_name in data["domains"]:
        class_names = ontology.find_class_names(domain_name)
        print("   %-6s %4d classes" % (domain_name, len(class_names)))
        domains.append({"name": domain_name, "classes": class_names})
    return {"domains": domains}


def step3_find_attributes(ontology, data):
    infra_attributes = ontology.find_infra_attributes()
    domains = []
    for domain in data["domains"]:
        domain_name = domain["name"]
        attributes_by_class = ontology.find_attributes_by_class(domain_name)

        classes = []
        attribute_count = 0
        for class_name in domain["classes"]:
            all_attribute_names = attributes_by_class.get(class_name, [])

            # INFRA keeps everything. The other domains do not repeat what INFRA has.
            if domain_name == "INFRA":
                left_out = set()
            else:
                left_out = infra_attributes.get(class_name, set())

            attributes = []
            for attribute_name in all_attribute_names:
                if attribute_name in left_out:
                    continue
                attributes.append({"name": attribute_name})

            # A class without own attributes is kept only if it never had any
            # and no other class inherits from it.
            if len(attributes) == 0:
                never_had_attributes = (len(all_attribute_names) == 0)
                if not (never_had_attributes and not ontology.has_subclass(class_name)):
                    continue

            classes.append({"name": class_name, "attributes": attributes})
            attribute_count = attribute_count + len(attributes)
        print("   %-6s %4d classes, %4d attributes" % (domain_name, len(classes), attribute_count))
        domains.append({"name": domain_name, "classes": classes})
    return {"domains": domains}


def find_kind(ontology, shacl, domain_name, class_name, attribute_name):
    """
    Decides the kind of ONE attribute. Returns (kind, target).
    kind is reference / composition / enumType / dataType, a TODO_ marker, or None.
    """
    list_name_in_ontology = ontology.get_list_name(attribute_name)

    # 1. Ask the SHACL (only for links to other things)
    link = None
    if ontology.is_link(attribute_name):
        link = shacl.get_link(domain_name, class_name, attribute_name)

    if link is not None and link[0] in ("reference", "composition"):
        kind = link[0]
        target = ontology.add_domain_prefix(link[1], domain_name)
        return kind, target

    # 2. A fixed list. The name from the SHACL message wins, otherwise the name from the ontology.
    if list_name_in_ontology is not None:
        if link is not None and link[1] is not None:
            return "enumType", link[1]
        return "enumType", list_name_in_ontology

    # 3. A plain value
    if ontology.has_plain_type(attribute_name):
        return "dataType", True

    # 4. A link, but nobody can say what it is
    if ontology.is_link(attribute_name):
        if link is None:
            return "TODO_linkKind", True         # the SHACL has no usable rule
        if link[1] is not None:
            return "enumType", link[1]
        return "TODO_enumType", True             # a list, but no name found

    return None, None


def step4_find_kinds(ontology, shacl, data):
    domains = []
    todo_attributes = []
    dropped_attributes = []
    for domain in data["domains"]:
        domain_name = domain["name"]
        counts = {}
        classes = []
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]
            attributes = []
            for attribute in class_entry["attributes"]:
                attribute_name = attribute["name"]
                kind, target = find_kind(ontology, shacl, domain_name, class_name, attribute_name)
                if kind is None:
                    dropped_attributes.append(domain_name + " " + class_name + "." + attribute_name)
                    continue
                attributes.append({"name": attribute_name, kind: target})
                counts[kind] = counts.get(kind, 0) + 1
                if kind.startswith("TODO"):
                    todo_attributes.append(domain_name + " " + class_name + "." + attribute_name + "  (" + kind + ")")
            classes.append({"name": class_name, "attributes": attributes})
        domains.append({"name": domain_name, "classes": classes})

        line = ""
        for kind in sorted(counts):
            line = line + "  " + kind + " " + str(counts[kind])
        print("   %-6s%s" % (domain_name, line))

    print()
    print("   TODO (no usable SHACL rule, the ontology cannot decide):", len(todo_attributes))
    for text in todo_attributes[:15]:
        print("      ", text)
    print("   attributes dropped (not a link and not a plain value):", len(dropped_attributes))
    for text in dropped_attributes[:10]:
        print("      ", text)
    print("   unusual SHACL rules noticed:", len(shacl.unusual_rules))
    for where, text in shacl.unusual_rules[:15]:
        print("      ", where, "-", text)
    return {"domains": domains}


def step5_give_ids(shacl, data):
    # Rule: a class gets the attribute "id" (intId 1) UNLESS one of its attributes
    # has sh:order 1. That attribute already is number 1. (References do not matter any more.)

    # 1. Which classes have an attribute with sh:order 1? (all domains together)
    has_order_one = {}                           # class name -> first place with sh:order 1
    for domain in data["domains"]:
        for class_entry in domain["classes"]:
            for attribute in class_entry["attributes"]:
                order = shacl.get_sh_order(domain["name"], class_entry["name"], attribute["name"])
                if order == 1:
                    if class_entry["name"] not in has_order_one:
                        has_order_one[class_entry["name"]] = domain["name"] + " " + class_entry["name"] + "." + attribute["name"]

    # 2. Every other class gets the attribute "id" (in every domain copy).
    ids_given = 0
    class_count = 0
    for domain in data["domains"]:
        for class_entry in domain["classes"]:
            class_count = class_count + 1
            class_name = class_entry["name"]
            if class_name in has_order_one:
                continue
            if len(class_entry["attributes"]) == 0:
                continue                              # a class without attributes gets no id
            already_has_id = False
            for attribute in class_entry["attributes"]:
                if attribute["name"] == "id":
                    already_has_id = True
            if not already_has_id:
                class_entry["attributes"].insert(0, {"name": "id", "dataType": True})
                ids_given = ids_given + 1

    print("   classes with an attribute that has sh:order 1 (no id):", len(has_order_one))
    for class_name in sorted(has_order_one)[:10]:
        print("      ", class_name, "(", has_order_one[class_name], ")")
    print("   id attributes added (one per copy of the class):", ids_given, "of", class_count, "classes")
    return data


def step6_number_attributes(shacl, data):
    from_order_count = 0
    by_position_count = 0
    double_numbers = []
    for domain in data["domains"]:
        domain_name = domain["name"]
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]
            numbers = {}                         # attribute name -> intId

            # The numbers we know: id is 1, the others have a sh:order.
            for attribute in class_entry["attributes"]:
                attribute_name = attribute["name"]
                if attribute_name == "id":
                    numbers[attribute_name] = 1
                else:
                    order = shacl.get_sh_order(domain_name, class_name, attribute_name)
                    if order is not None:
                        numbers[attribute_name] = order
                        from_order_count = from_order_count + 1

            # Attributes without sh:order get the next free numbers.
            next_number = 1
            if len(numbers) > 0:
                next_number = max(numbers.values()) + 1
            for attribute in class_entry["attributes"]:
                if attribute["name"] not in numbers:
                    numbers[attribute["name"]] = next_number
                    next_number = next_number + 1
                    by_position_count = by_position_count + 1

            # Put the intId first in every attribute and sort by intId.
            numbered_attributes = []
            for attribute in class_entry["attributes"]:
                numbered = {"intId": numbers[attribute["name"]]}
                numbered.update(attribute)
                numbered_attributes.append(numbered)
            numbered_attributes.sort(key=get_int_id)
            class_entry["attributes"] = numbered_attributes

            # Is a number used twice?
            used_numbers = set()
            for attribute in numbered_attributes:
                if attribute["intId"] in used_numbers:
                    double_numbers.append(domain_name + " " + class_name + ": intId " + str(attribute["intId"]) + " is used twice")
                    break
                used_numbers.add(attribute["intId"])

    print("   intId taken from sh:order:", from_order_count)
    print("   intId numbered by us (no sh:order):", by_position_count)
    print("   classes where one intId is used twice:", len(double_numbers))
    for text in double_numbers[:10]:
        print("      ", text)
    return data


def step7_add_multiplicity(shacl, data):
    # Multiplicity is the next step after the numbers.
    # We write it for every attribute that has a SHACL rule (not for "id").
    written = 0
    union_skipped = 0
    without_rule = []
    counts = {}
    for domain in data["domains"]:
        domain_name = domain["name"]
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]
            class_is_union = shacl.is_union(domain_name, class_name)
            for attribute in class_entry["attributes"]:
                if attribute["name"] == "id":
                    continue
                multiplicity = shacl.get_multiplicity(domain_name, class_name, attribute["name"])
                if multiplicity is None:
                    without_rule.append(domain_name + " " + class_name + "." + attribute["name"])
                    continue
                counts[multiplicity] = counts.get(multiplicity, 0) + 1
                if multiplicity == "1..1":
                    continue                              # 1..1 is the normal case, it is not written
                if class_is_union and multiplicity == "0..1":
                    union_skipped = union_skipped + 1
                    continue                              # union class: "at most one" is already said by union = true
                attribute["multiplicity"] = multiplicity
                written = written + 1
    print("   multiplicity written:", written, "(1..1 is not written)")
    print("   0..1 not written in union classes (union = true says it):", union_skipped)
    print("   how often each value was found in the SHACL:")
    for multiplicity in sorted(counts, key=lambda text: -counts[text])[:8]:
        note = ""
        if multiplicity == "1..1":
            note = "   <- found, but not written"
        print("      %-8s %4d%s" % (multiplicity, counts[multiplicity], note))
    print("   attributes without SHACL rule (no multiplicity):", len(without_rule))
    for text in without_rule[:8]:
        print("      ", text)
    return data


def step8_add_data_details(ontology, shacl, data):
    # Plain values (dataType): the real type, the unit and the range.
    typed = 0
    with_unit = 0
    with_range = 0
    unknown_types = set()
    unknown_units = set()
    without_type = []
    for domain in data["domains"]:
        domain_name = domain["name"]
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]
            for attribute in class_entry["attributes"]:
                attribute_name = attribute["name"]
                if attribute_name == "id":
                    attribute["dataType"] = "string"          # the identity is always a text
                    continue
                if "dataType" not in attribute:
                    continue
                xsd_type = shacl.get_data_type(domain_name, class_name, attribute_name)
                if xsd_type is None:
                    without_type.append(domain_name + " " + class_name + "." + attribute_name)
                elif xsd_type in DATA_TYPE_NAMES:
                    attribute["dataType"] = DATA_TYPE_NAMES[xsd_type]
                    typed = typed + 1
                else:
                    attribute["dataType"] = xsd_type          # unknown type: keep the xsd name
                    unknown_types.add(xsd_type)
                unit_name = ontology.get_unit_name(attribute_name)
                if unit_name is not None:
                    if unit_name in UNIT_SYMBOLS:
                        attribute["unit"] = UNIT_SYMBOLS[unit_name]
                    else:
                        attribute["unit"] = unit_name         # unknown unit: keep the name
                        unknown_units.add(unit_name)
                    with_unit = with_unit + 1
                range_text = shacl.get_range(domain_name, class_name, attribute_name)
                if range_text is not None:
                    attribute["range"] = range_text
                    with_range = with_range + 1
    print("   dataType with a real type:", typed)
    print("   units written:", with_unit, "  ranges written:", with_range)
    print("   plain values without sh:datatype (left as true):", len(without_type))
    for text in without_type[:8]:
        print("      ", text)
    print("   xsd types without a name in DATA_TYPE_NAMES:", sorted(unknown_types))
    print("   units without a symbol in UNIT_SYMBOLS:", sorted(unknown_units))
    return data


def step9_add_order_and_notes(ontology, shacl, data):
    # "ordered" (byIndex / byKey) and "formatNote" for the attributes that have them.
    ordered_written = 0
    ordered_from_shacl = 0
    notes_written = 0
    for domain in data["domains"]:
        domain_name = domain["name"]
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]
            for attribute in class_entry["attributes"]:
                attribute_name = attribute["name"]
                if attribute_name == "id":
                    continue
                # 1. ordered: the SHACL knows byIndex (a list), the ontology knows byKey and byIndex
                if shacl.is_ordered_by_index(domain_name, class_name, attribute_name):
                    attribute["ordered"] = "byIndex"
                    ordered_from_shacl = ordered_from_shacl + 1
                    ordered_written = ordered_written + 1
                else:
                    ordered = ontology.get_ordered(attribute_name)
                    if ordered is not None:
                        attribute["ordered"] = ordered
                        ordered_written = ordered_written + 1
                # 2. formatNote: only the ontology has it
                note = ontology.get_format_note(attribute_name)
                if note is not None:
                    attribute["formatNote"] = note
                    notes_written = notes_written + 1
    print("   ordered written:", ordered_written, "(", ordered_from_shacl, "found in the SHACL )")
    print("   formatNote written:", notes_written)
    return data


def step10_add_texts(ontology, shacl, data):
    # info, label, key, exp, subsetName, ontology (subPropertyOf, subClassOf, property types), sameKeyAs.
    counts = {"sub-package": 0, "union": 0, "label": 0, "key": 0, "info": 0, "class info": 0, "exp": 0, "subsetName": 0, "ontology": 0, "class ontology": 0, "sameKeyAs": 0}
    without_info = []

    # which class copies have an id? (needed for sameKeyAs)
    has_id = {}
    for domain in data["domains"]:
        for class_entry in domain["classes"]:
            for attribute in class_entry["attributes"]:
                if attribute["name"] == "id":
                    has_id[(domain["name"], class_entry["name"])] = True

    for domain in data["domains"]:
        domain_name = domain["name"]
        for class_entry in domain["classes"]:
            class_name = class_entry["name"]

            # --- the class itself
            text = shacl.get_class_description(domain_name, class_name)     # info = sh:description of the class form
            if text is not None:
                class_entry["info"] = text
                counts["class info"] = counts["class info"] + 1
            sub_package = shacl.get_sub_package(domain_name, class_name)
            if sub_package is not None:
                class_entry["belongsToSubPackage"] = sub_package
                counts["sub-package"] = counts["sub-package"] + 1
            if shacl.is_union(domain_name, class_name):
                class_entry["union"] = True
                counts["union"] = counts["union"] + 1
            parents = ontology.get_super_classes(class_name)
            if len(parents) == 1:
                class_entry["ontology"] = {"subClassOf": parents[0]}
                counts["class ontology"] = counts["class ontology"] + 1
            elif len(parents) > 1:
                class_entry["ontology"] = {"subClassOf": parents}
                counts["class ontology"] = counts["class ontology"] + 1

            # --- the attributes
            for attribute in class_entry["attributes"]:
                attribute_name = attribute["name"]

                if attribute_name == "id":
                    attribute["info"] = ID_INFO
                    attribute["key"] = "global"            # every id is a global key
                    counts["key"] = counts["key"] + 1
                    # sameKeyAs, case 1: the same class also lives in INFRA and has an id there
                    if domain_name != "INFRA" and ("INFRA", class_name) in has_id:
                        attribute["sameKeyAs"] = "infra." + class_name
                        counts["sameKeyAs"] = counts["sameKeyAs"] + 1
                    # No sameKeyAs for the case "topoArea -> infra.TopoArea" (the reference in intId 2) and none for same-domain cases
                    continue

                text = shacl.get_description(domain_name, class_name, attribute_name)     # info = sh:description
                if text is not None:
                    attribute["info"] = text
                    counts["info"] = counts["info"] + 1
                else:
                    without_info.append(domain_name + " " + class_name + "." + attribute_name)

                label = ontology.get_label(attribute_name)
                if label is not None:
                    attribute["label"] = label
                    counts["label"] = counts["label"] + 1

                key = ontology.get_key(attribute_name)
                if key is not None:
                    attribute["key"] = key
                    counts["key"] = counts["key"] + 1

                # regex is not written any more (decided: ignore regex)

                exp = ontology.get_exp(attribute_name)
                if exp is not None:
                    attribute["exp"] = exp
                    counts["exp"] = counts["exp"] + 1

                subset_name = ontology.get_subset_name(attribute_name)
                if subset_name is not None:
                    attribute["subsetName"] = subset_name
                    counts["subsetName"] = counts["subsetName"] + 1

                super_properties = ontology.get_super_properties(attribute_name)
                property_types = ontology.get_property_types(attribute_name)
                if len(super_properties) > 0 or len(property_types) > 0:
                    ontology_info = {}
                    if len(super_properties) == 1:
                        ontology_info["subPropertyOf"] = super_properties[0]
                    elif len(super_properties) > 1:
                        ontology_info["subPropertyOf"] = super_properties
                    if len(property_types) == 1:
                        ontology_info["propertyType"] = property_types[0]
                    elif len(property_types) > 1:
                        ontology_info["propertyTypes"] = property_types
                    attribute["ontology"] = ontology_info
                    counts["ontology"] = counts["ontology"] + 1

    for name in counts:
        print("   %-15s %4d" % (name, counts[name]))
    print("   attributes without a SHACL description (no info):", len(without_info))
    for text in without_info[:8]:
        print("      ", text)
    return data


def step11_fill_value_lists(shacl, skos, data, wanted_domains):
    # wanted_domains: the domains the user asked for. An empty list means all domains.
    names_from_skos = 0
    names_from_code = []
    lists_without_values = []
    ids_from_position = []                                # values without a number in the SKOS label
    ids_used_twice = []                                   # a number used twice inside one list

    for domain in data["domains"]:
        domain_name = domain["name"]
        if len(wanted_domains) > 0 and domain_name not in wanted_domains:
            continue                                  # the user did not ask for this domain

        # Which attributes use which list?
        list_users = {}                          # list name -> [(class name, attribute name), ...]
        for class_entry in domain["classes"]:
            for attribute in class_entry["attributes"]:
                if "enumType" in attribute:
                    list_name = attribute["enumType"]
                    if list_name not in list_users:
                        list_users[list_name] = []
                    list_users[list_name].append((class_entry["name"], attribute["name"]))

        # A full copy of every list this domain uses.
        enums = []
        for list_name in sorted(list_users):
            addresses = None
            for class_name, attribute_name in list_users[list_name]:
                addresses = shacl.get_value_addresses(domain_name, class_name, attribute_name)
                if addresses is not None:
                    break
            if addresses is None:
                addresses = []
                lists_without_values.append(domain_name + ": " + list_name)

            values = []
            used_numbers = set()
            for position, address in enumerate(addresses):
                value_name, found = skos.get_value_name(address)
                if found:
                    names_from_skos = names_from_skos + 1
                else:
                    names_from_code.append(list_name + ": " + value_name)
                # intId = the number at the end of the SKOS label (CCSTMS_CD_80mm_1 -> 1).
                # Only if the value has no such number, the position in the SHACL list is used.
                int_id = skos.get_value_index(address)
                if int_id is None:
                    int_id = position
                    ids_from_position.append(list_name + ": " + value_name)
                if int_id in used_numbers:
                    ids_used_twice.append(domain_name + " " + list_name + ": intId " + str(int_id))
                used_numbers.add(int_id)
                values.append({"intId": int_id, "name": value_name, "owl:sameAs": address})
            enums.append({"name": list_name, "enumLiterals": values})

        # Write the final file of this domain.
        classes = []
        attribute_count = 0
        for class_entry in domain["classes"]:
            struct = {"name": class_entry["name"]}
            if "info" in class_entry:
                struct["info"] = class_entry["info"]
            if "ontology" in class_entry:
                struct["ontology"] = class_entry["ontology"]
            if "belongsToSubPackage" in class_entry:
                struct["belongsToSubPackage"] = class_entry["belongsToSubPackage"]
            if "union" in class_entry:
                struct["union"] = class_entry["union"]
            struct["attrs"] = class_entry["attributes"]
            classes.append(struct)
            attribute_count = attribute_count + len(class_entry["attributes"])
        file_name = "kinds_" + domain_name + ".json"
        save_json(file_name, {"domain": domain_name, "structs": classes, "enums": enums})
        print("      %-6s %4d classes, %4d attributes, %3d value lists" % (domain_name, len(classes), attribute_count, len(enums)))

    print()
    print("   value names taken from the SKOS labels:", names_from_skos)
    print("   value names without SKOS label (the code is used):", len(names_from_code))
    for text in names_from_code[:6]:
        print("      ", text)
    print("   lists with no values at all (no sh:in found):", len(lists_without_values))
    for text in lists_without_values[:8]:
        print("      ", text)
    print("   intId taken from the SKOS label number:", names_from_skos - len(ids_from_position))
    print("   intId without a number in the SKOS label (position in the list is used):", len(ids_from_position))
    for text in ids_from_position[:6]:
        print("      ", text)
    print("   a number used twice inside one list:", len(ids_used_twice))
    for text in ids_used_twice[:8]:
        print("      ", text)


# ================================================================== main
def main():
    first_step = 1
    words = []                                       # the domain names the user typed
    for argument in sys.argv[1:]:
        if argument.isdigit():
            first_step = int(argument)
        elif argument in ("-h", "--help", "help"):
            print(__doc__)
            return
        else:
            words.append(argument)

    ontology = Ontology(ONTOLOGY_FILE)

    # Turn the typed words into real domain names (infra -> INFRA, ss026 -> ss026).
    all_domains = ontology.find_domain_names()
    wanted_domains = []
    for word in words:
        found = None
        for domain_name in all_domains:
            if domain_name.lower() == word.lower():
                found = domain_name
        if found is None:
            print("Unknown domain:", word)
            print("The domains in the ontology are:", ", ".join(all_domains))
            return
        if found not in wanted_domains:
            wanted_domains.append(found)
    if first_step < 1 or first_step > 11:
        print("The step must be a number from 1 to 11.")
        return
    if len(wanted_domains) > 0:
        print("Final files will be written for:", ", ".join(wanted_domains))
    else:
        print("Final files will be written for all domains:", ", ".join(all_domains))
    shacl = ShaclRules(SHACL_FOLDER)
    skos = SkosLabels(SKOS_FOLDER)
    print("SHACL files found:", len(shacl.files))
    if len(shacl.files) == 0:
        print("WARNING: no *-shapes_*.ttl file in", os.path.abspath(SHACL_FOLDER))
        print("         Without them the kinds cannot be decided and the lists have no values.")
    print("SKOS files with", LABEL_START, "labels:", skos.file_count, "(", len(skos.labels), "values )")
    if skos.file_count == 0:
        print("WARNING: no SKOS file found in", os.path.abspath(SKOS_FOLDER), "- the value names will be codes (80, 100 ...).")
    print()

    data = None
    if first_step > 1:
        data = load_json(STEP_FILES[first_step - 1])

    if first_step <= 1:
        print("STEP 1 - find the domains")
        data = step1_find_domains(ontology)
        save_json(STEP_FILES[1], data)
        print()
    if first_step <= 2:
        print("STEP 2 - find the classes of every domain")
        data = step2_find_classes(ontology, data)
        save_json(STEP_FILES[2], data)
        print()
    if first_step <= 3:
        print("STEP 3 - find the attributes of every class")
        data = step3_find_attributes(ontology, data)
        save_json(STEP_FILES[3], data)
        print()
    if first_step <= 4:
        print("STEP 4 - decide the kind of every attribute")
        data = step4_find_kinds(ontology, shacl, data)
        save_json(STEP_FILES[4], data)
        print()
    if first_step <= 5:
        print("STEP 5 - give an id to every class without sh:order 1")
        data = step5_give_ids(shacl, data)
        save_json(STEP_FILES[5], data)
        print()
    if first_step <= 6:
        print("STEP 6 - number the attributes (intId)")
        data = step6_number_attributes(shacl, data)
        save_json(STEP_FILES[6], data)
        print()
    if first_step <= 7:
        print("STEP 7 - add the multiplicity")
        data = step7_add_multiplicity(shacl, data)
        save_json(STEP_FILES[7], data)
        print()
    if first_step <= 8:
        print("STEP 8 - add the real data type, unit and range")
        data = step8_add_data_details(ontology, shacl, data)
        save_json(STEP_FILES[8], data)
        print()
    if first_step <= 9:
        print("STEP 9 - add ordered and formatNote")
        data = step9_add_order_and_notes(ontology, shacl, data)
        save_json(STEP_FILES[9], data)
        print()
    if first_step <= 10:
        print("STEP 10 - add info, label, key, exp, subsetName, ontology, sameKeyAs, sub-package and union")
        data = step10_add_texts(ontology, shacl, data)
        save_json(STEP_FILES[10], data)
        print()
    if first_step <= 11:
        print("STEP 11 - fill in the value lists and write the final files")
        step11_fill_value_lists(shacl, skos, data, wanted_domains)
        print()
    print("Done.")


main()