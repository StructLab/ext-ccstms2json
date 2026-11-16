# Ontology to JSON

`Ontology_to_JSON.py` reads the ERA/CCS-TMS ontology, the SHACL shape files and the SKOS value lists,
and writes **one JSON file per domain** (INFRA, ENG, MAP, OPP, TP, ss026).

The program works in 11 small steps. Each step reads the file written by the step before,
adds one thing, and writes a new file. You can start at any step and you can choose the domain.

## What is in this repository

```
Ontology-Json/
  Ontology_to_JSON.py    the program
  ontology.ttl           the ontology
  SHACL_shape/           the SHACL shape files (*-shapes_*.ttl)
  skos/                  the SKOS value lists (*.ttl)
  Final_Output/          the final JSON files, one per domain (kinds_<DOMAIN>.json)
```

## What you need

- Python 3.8 or newer
- the library `rdflib`:

```
pip install rdflib
```

## How to run

Open a terminal in the repository folder and run:

```
python Ontology_to_JSON.py              all 11 steps, all domains
python Ontology_to_JSON.py 4            start at step 4, run steps 4 to 11
python Ontology_to_JSON.py infra        all steps, write only kinds_INFRA.json
python Ontology_to_JSON.py eng          all steps, write only kinds_ENG.json
python Ontology_to_JSON.py 7 eng        start at step 7, write only kinds_ENG.json
python Ontology_to_JSON.py infra eng    write the final files of INFRA and ENG
python Ontology_to_JSON.py help         show the instructions
```

- A number is the first step to run (1 to 11).
- A word is a domain name. Capital letters do not matter.
- Steps 1 to 10 always work on all domains, because some rules look at INFRA
  (for example `sameKeyAs`, and ENG does not repeat what INFRA already has).
  Only the final files of step 11 are limited to the domains you chose.
- To start at step N, the file of step N-1 must exist (see the table below).

## The settings

At the top of `Ontology_to_JSON.py` (lines 49 to 51):

```python
ONTOLOGY_FILE = "ontology.ttl"
SHACL_FOLDER = "SHACL_shape"
SKOS_FOLDER = "skos"
```

The paths are relative to the folder where you start the program.
Change them if your files are somewhere else.

## The 11 steps

| Step | What it does | File it writes |
| --- | --- | --- |
| 1 | find the domains | `step1_domains.json` |
| 2 | find the classes of every domain | `step2_classes.json` |
| 3 | find the attributes of every class | `step3_attributes.json` |
| 4 | decide the kind of every attribute (reference, composition, enumType, dataType) | `step4_kinds.json` |
| 5 | give the attribute `id` to every class that has no `sh:order 1` | `step5_ids.json` |
| 6 | number the attributes (`intId`) | `step6_numbers.json` |
| 7 | add the multiplicity (`1..1` is not written) | `step7_multiplicity.json` |
| 8 | add the real data type, unit and range | `step8_details.json` |
| 9 | add `ordered` and `formatNote` | `step9_order_notes.json` |
| 10 | add info, label, key, exp, subsetName, ontology, sameKeyAs, sub-package, union | `step10_texts.json` |
| 11 | fill in the value lists and write the final files | `kinds_<DOMAIN>.json` |

The step files and the final files are written into the folder where you start the program.

## Where each piece of information comes from

| Information | Source |
| --- | --- |
| domains, classes, attribute names | ontology (`era:ccsView` marks the domain) |
| kind (reference, composition, enumType, dataType) | SHACL |
| `intId` | SHACL `sh:order`, otherwise the next free number |
| `multiplicity` | SHACL (`sh:minCount`, `sh:maxCount`, list item count rule) |
| data type, `range` | SHACL (`sh:datatype`, `sh:minInclusive`, `sh:maxInclusive`) |
| `unit`, `ordered`, `formatNote` | ontology (`ordered` is `byIndex` when the SHACL says so) |
| `info` | SHACL `sh:description` |
| `label`, `key`, `exp`, `subsetName` | ontology |
| `ontology` (`subClassOf`, `subPropertyOf`, property types) | ontology |
| `belongsToSubPackage`, `union` | SHACL |
| values of a list and their order | SHACL `sh:in` |
| name of a value | SKOS hidden label that starts with `CCSTMS_` |

Each domain uses the shapes file of its own domain (`infra-shapes_*.ttl` for INFRA and so on).

## The rules in short

- **id:** every class that has attributes gets the attribute `id` with `intId 1`,
  except a class that has an attribute with `sh:order 1`. `id` is a global key.
- **sameKeyAs:** only for a class in another domain that also has an `id` in INFRA
  (`infra.<ClassName>`).
- **Value lists:** every domain file has a full copy of every list it uses.
  The values and their order come from the SHACL. The name of a value comes from the SKOS label,
  without `CCSTMS_` and without the index at the end (`CCSTMS_CD_80mm_1` becomes `CD_80mm`).
  If there is no label, the code at the end of the address is used.
  Every value has `intId` (position in the list, counted from 0), `name` and `owl:sameAs` (its address).
- **subsetName / subPropertyOf:** everything that is in the ontology is written.
  With more than one value the output is a list.
- **regex:** not written.

## The output

Each `kinds_<DOMAIN>.json` file looks like this:

```json
{
 "domain": "INFRA",
 "structs": [
  {
   "name": "BufferStop",
   "info": "...",
   "attrs": [
    {"intId": 1, "name": "id", "dataType": "string", "key": "global", "info": "..."},
    {"intId": 2, "name": "...", "multiplicity": "0..1", "...": "..."}
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

`structs` are the classes with their attributes (`attrs`). `enums` are the value lists.

## If something looks wrong

The first lines of the output show how many SHACL files and SKOS files were found.
If a number is 0, check the folder names in the settings.