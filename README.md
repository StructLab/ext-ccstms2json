# Ontology to JSON

Reads the CCS-TMS ontology, the SHACL shapes and the SKOS value lists, and writes **one JSON file per domain** (INFRA, ENG, MAP, OPP, TP, ss026).


## Quick start

1. Install Python 3.8 or newer.
2. Install the library: `pip install rdflib`
3. Open a terminal in the repository folder.
4. Run: `python Ontology_to_JSON.py`
5. The result files are written into the folder where you start the program.

## Usage

- `python Ontology_to_JSON.py` runs all 11 steps for all domains.
- `python Ontology_to_JSON.py infra` writes only `kinds_INFRA.json`.
- `python Ontology_to_JSON.py eng` writes only `kinds_ENG.json`.
- `python Ontology_to_JSON.py infra eng` writes the files of INFRA and ENG.
- `python Ontology_to_JSON.py 7` starts at step 7. It needs the file of step 6.
- `python Ontology_to_JSON.py 7 eng` starts at step 7 and writes only `kinds_ENG.json`.
- `python Ontology_to_JSON.py help` shows the instructions.

A number is the first step (1 to 11). A word is a domain name, and capital letters do not matter.
Steps 1 to 10 always run for all domains, because some rules look at INFRA. Only the final files are limited to the domains you choose.

## Repository

- `Ontology_to_JSON.py`: the program.
- `ontology.ttl`: the ontology.
- `SHACL_shape/`: the SHACL shape files (`*-shapes_*.ttl`).
- `skos/`: the SKOS value lists.
- `Final_Output/`: the final JSON files.

The folders are set at the top of `Ontology_to_JSON.py` (lines 49 to 51). The paths are relative to the folder where you start the program:

```python
ONTOLOGY_FILE = "ontology.ttl"
SHACL_FOLDER = "SHACL_shape"
SKOS_FOLDER = "skos"
```

## The 11 steps

Each step reads the file of the step before, adds one thing, and writes a new file.

1. Find the domains. Writes `step1_domains.json`.
2. Find the classes of every domain. Writes `step2_classes.json`.
3. Find the attributes of every class. Writes `step3_attributes.json`.
4. Decide the kind of every attribute: reference, composition, enumType or dataType. Writes `step4_kinds.json`.
5. Give the attribute `id`. Writes `step5_ids.json`.
6. Number the attributes (`intId`). Writes `step6_numbers.json`.
7. Add the multiplicity. Writes `step7_multiplicity.json`.
8. Add the real data type, unit and range. Writes `step8_details.json`.
9. Add `ordered` and `formatNote`. Writes `step9_order_notes.json`.
10. Add info, label, key, exp, subsetName, ontology, sameKeyAs, sub-package and union. Writes `step10_texts.json`.
11. Fill in the value lists and write the final files `kinds_<DOMAIN>.json`.

## Where the information comes from

From the ontology:
- the domains (`era:ccsView` marks the domain), the classes and the attribute names
- `unit`, `ordered`, `formatNote`, `label`, `key`, `exp` and `subsetName`
- the `ontology` field: `subClassOf`, `subPropertyOf` and the property types

From the SHACL:
- the kind of the attribute, `multiplicity`, the data type, `range` and `info` (`sh:description`)
- `belongsToSubPackage` and `union`
- `intId` (`sh:order`). If there is none, the next free number is used.
- the values of a list and their order (`sh:in`)

From the SKOS files:
- the name of a value: the hidden label that starts with `CCSTMS_`

Each domain uses the shapes file of its own domain (`infra-shapes_*.ttl` for INFRA and so on).

## Rules

- **`id`:** every class that has attributes gets `id` with `intId 1`, except a class that has an attribute with `sh:order 1`. `id` is a global key.
- **`multiplicity`:** `1..1` is not written. In a union class (`sh:xone`) the attributes get no multiplicity, because `union: true` already says that at most one is used.
- **`sameKeyAs`:** only for a class in another domain that also has an `id` in INFRA (`infra.<ClassName>`).
- **Value lists:** every domain file has a full copy of every list it uses.
  - A value has `intId` (the number at the end of the SKOS hidden label), `name` and `owl:sameAs` (its address).
  - The name is the SKOS label without `CCSTMS_` and without the index at the end (`CCSTMS_CD_80mm_1` becomes `CD_80mm`).
  - Without a label, the code at the end of the address is used.
- **`subsetName`, `subPropertyOf`:** everything that is in the ontology is written. With more than one value the output is a list.
- **`regex`:** not written.

## Output

```json
{
 "domain": "INFRA",
 "structs": [
  {
   "name": "BufferStop",
   "attrs": [
    {"intId": 1, "name": "id", "dataType": "string", "key": "global"}
   ]
  }
 ],
 "enums": [
  {
   "name": "ArcType",
   "enumLiterals": [
    {"intId": 0, "name": "circularArc", "owl:sameAs": "http://data.europa.eu/949/concepts/arc-type/circularArc"}
   ]
  }
 ]
}
```

`structs` are the classes with their attributes (`attrs`). `enums` are the value lists. The example is shortened.

## Troubleshooting

The first lines of the output show how many SHACL files and SKOS files were found. If a number is 0, check the folder names in the settings.