import argparse
import yaml
import sys
import logging
import glob
from datetime import datetime


def get_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description="Script to convert AIRR openapi3 schema to LinkML")

    parser.add_argument("-a", "--airr_schema_yaml", type=str, help="Input openapi3 YAML file",
                        default="../../airr_schema/airr-standards-v2.0/specs/airr-schema-openapi3.yaml")
    parser.add_argument("-o", "--output_file", type=str, help="Output file to write the LinkML to",
                            default="../../vdjserver_airr_schema/schema/vdjserver_airr_schema.yaml")
    parser.add_argument("-s", "--superclass",  type=str, help="Superclass name (will be referenced for each class under 'is_a')", default="AIRRStandards")

    return parser.parse_args()

def get_airr_yaml(file_location):
    with open(parsed_args.airr_schema_yaml) as file:
        airr_yaml = yaml.safe_load(file)
    return airr_yaml

def snake_to_camel_case(word):
    new_word = ''.join('_' if x == '' else x.capitalize() for x in word.split('_'))
    return new_word

def is_deprecated(slot_yaml):    
    return "x-airr" in slot_yaml and "deprecated" in slot_yaml["x-airr"] and slot_yaml["x-airr"]["deprecated"] == True

def get_slot_range(slot_name, slot_yaml):
    if slot_yaml.get("type") == "array":
        return get_slot_range(slot_name=slot_name, slot_yaml= slot_yaml["items"])
    elif "enum" in slot_yaml:
        return f"{snake_to_camel_case(slot_name)}Enum"
    elif "$ref" in slot_yaml:
        ref = slot_yaml["$ref"]
        if ref == "#/Ontology":
            return f"{snake_to_camel_case(slot_name)}Ontology"
        else:
            return f"{ref.lstrip('#/')}"
        
    slot_type = slot_yaml.get("type")

    if slot_type =="string":
        fmt = slot_yaml.get("format")
        if fmt == "date":
            return "date"
        if fmt == "date-time":
            return "datetime"
        return "string"
    
    if slot_type == "integer":
        return "integer"

    if slot_type == "number":
        return "float"

    if slot_type == "boolean":
        return "boolean"

    if slot_type == "object":
        print(f" Error: Cannot determine range for slot: ({slot_name}) omitting range")
        return None
    
    raise NotImplementedError(slot_yaml)

def is_array(slot_yaml):
    if slot_yaml.get("type") == "array":
        return True
    else:
        return False

def is_multivalued(slot_yaml):
    return is_array(slot_yaml) or "additionalProperties" in slot_yaml

def get_slot_annotation(slot_yaml):
    annotations = dict()

    if "nullable" in slot_yaml:
        annotations["nullable"] = slot_yaml["nullable"]

    if "x-airr" in slot_yaml:
        if "nullable" in slot_yaml["x-airr"]:
            assert "nullable" not in annotations or annotations["nullable"] == slot_yaml["x-airr"]["nullable"], \
                f"Found contradicting values for nullable in: {slot_yaml}"
            annotations["nullable"] = slot_yaml["x-airr"]["nullable"]

    return annotations

def get_slot(slot_name, slot_yaml, keyword):
    if is_deprecated(slot_yaml):
        return dict(), None

    # Used for Tree/nodes only
    if "additionalProperties" in slot_yaml and type(slot_yaml["additionalProperties"]) == dict:
        slot_yaml = {**slot_yaml["additionalProperties"], **slot_yaml}
    
    identifier_slot = None
    if "x-airr" in slot_yaml:
        if slot_yaml["x-airr"].get("class-identifier") is True:
            identifier_slot = slot_name

    slot = {
        slot_name:{
            "name": slot_name,
            "description": slot_yaml.get("description", f"Default {slot_name} description").strip()
        }
    }
    if slot_name.endswith("_type"):
        slot[slot_name]["slot_uri"] = "rdf:type"

    slot_range = get_slot_range(slot_name, slot_yaml)

    if slot_range:
        slot[slot_name]["range"] = slot_range
    if is_multivalued(slot_yaml):
        slot[slot_name]["multivalued"] = True

    
    annotations = get_slot_annotation(slot_yaml)
    if len(annotations) > 0:
        slot[slot_name]["annotations"] = annotations
    return slot, identifier_slot



def get_all_slots(airr_yaml, keyword) -> dict:
    all_slots = {}
    identifier_slot = None
    print(f"{keyword}")
    for slot_name, slot_yaml in airr_yaml[keyword]["properties"].items():
        slot, id_slot = get_slot(slot_name, slot_yaml, keyword)
        all_slots.update(slot)
        if id_slot:
            if identifier_slot:
                raise ValueError(f"Multiple class identifiers found for {keyword}")
            identifier_slot = id_slot

    return all_slots, identifier_slot

def get_ontology_enum(base_name, slot_yaml, keyword):
    ontology_name = f"{base_name}Ontology"
    if "ontology" in slot_yaml["x-airr"]:
        source_node = slot_yaml["x-airr"]["ontology"]["top_node"]["id"]
        if source_node:
            return {
                "name": ontology_name,
                "reachable_from":{
                    "source_nodes": [source_node],
                    "include_self": True,
                    "relationship_types": ["rdfs:subClassOf"],
                }
            }
        else:
            print("Error: Source node for ontology '{base_name}' (in '{keyword}') was not defined, omitting 'reachable_from")
    else:
        print(f"** Error: Ontology '{base_name}' (in '{keyword}') does not follow the correct formatting, omitting 'reachable_from'...\n")
        
    return {"name": ontology_name}



def get_enum(base_name, slot_yaml, keyword):
    if slot_yaml.get("type") == "array":
        return get_enum(base_name, slot_yaml["items"], keyword)
    if "$ref" in slot_yaml:
        ref = slot_yaml["$ref"]
        if ref == "#/Ontology":
            return get_ontology_enum(base_name, slot_yaml, keyword)
        
    elif "enum" in slot_yaml:
        closed_vocabulary_enum = {
            "name": f"{base_name}Enum",
            "permissible_values":{
                enum_val: None for enum_val in slot_yaml["enum"]if enum_val is not None
            }
        }
        return closed_vocabulary_enum

def get_all_enums(keyword_yaml, keyword):
    all_enums = {}
    for slot_name, slot_yaml in keyword_yaml["properties"].items():
        if not is_deprecated(slot_yaml):
            base_name = snake_to_camel_case(slot_name)
            if base_name == "Property":
                pass
            new_enum = get_enum(base_name, slot_yaml, keyword)
            if new_enum:
                all_enums[new_enum["name"]] = new_enum
    return all_enums

def get_yaml_output_for_keyword(airr_yaml, keyword, linkml_superclass):
    output_slots, identifier_slot = get_all_slots(airr_yaml, keyword)
    
    class_name = keyword

    description = airr_yaml[keyword].get("description", f"Default {class_name} description")
    class_def = {
        "is_a": linkml_superclass,
        "description": description,
        "slots": list(output_slots.keys())
    }
    enums = get_all_enums(airr_yaml[keyword], keyword)

    if identifier_slot:
        class_def["slot_usage"] = {
            identifier_slot:{
                "identifier": True,
                "required": True
            }
        }

    yaml_output_dict = {
        "classes": {
            class_name: class_def,
        },
        "slots": output_slots,
        "enums": enums
    }
    
    return yaml_output_dict

def get_yaml_output_for_composition_keyword(airr_yaml, output_yaml, keyword, linkml_superclass):
    class_name = keyword
    description = airr_yaml[keyword].get("description", f"Default {class_name} description")
    composition_yaml = {
        "classes": {
            class_name:{
                "is_a": linkml_superclass,
                "description" : description,
                "slots": []
            },
        },
        "slots": {},
        "enums": {}
    }
    # Track class level identifier
    identifier_slot = None
    for class_yaml in airr_yaml[keyword]["allOf"]:
        if "$ref" in class_yaml:
            super_class_name = class_yaml["$ref"].lstrip("/#")
            composition_yaml["classes"][class_name]["slots"].extend(
                output_yaml["classes"][f"{super_class_name}"]["slots"]
            )
        else:
            new_slots, new_identifier = get_all_slots({keyword: class_yaml}, keyword)
            new_enums = get_all_enums(class_yaml, keyword)
            composition_yaml["slots"].update(new_slots)
            composition_yaml["enums"].update(new_enums)
            composition_yaml["classes"][class_name]["slots"].extend(list(new_slots.keys()))
            if new_identifier:
                identifier_slot = new_identifier
    if identifier_slot:
        composition_yaml["classes"][class_name]["slot_usage"] = {
            identifier_slot:{
                "identifier": True,
                "required": True
            }
        }
    return composition_yaml
    

def get_simple_keywords_to_process(airr_yaml, skip_keywords):
    simple_keywords = []
    for key, value in airr_yaml.items():
        if "type" in value.keys() and key not in skip_keywords:
            simple_keywords.append(key)
    return simple_keywords


def get_composition_keywords_to_process(airr_yaml, skip_keywords):
    composition_keywords = []
    for key, value in airr_yaml.items():
        if list(value.keys()) == ["allOf"] and key not in skip_keywords:
            composition_keywords.append(key)
    return composition_keywords


def get_differing_fields(yaml_pt1, yaml_pt2):
    return ([key for key in yaml_pt1 if key not in yaml_pt2] +
            [key for key in yaml_pt2 if key not in yaml_pt1] +
            [key for key in yaml_pt1 if key in yaml_pt2 and yaml_pt1[key] != yaml_pt2[key]])

def get_intersecting_yaml(yaml_pt1, yaml_pt2):
    final = {}
    for key in yaml_pt1:
        if key in yaml_pt2:
            if yaml_pt1[key] == yaml_pt2[key]:
                final[key] = yaml_pt1[key]
            elif type(yaml_pt1[key]) == dict and type(yaml_pt2[key]) == dict:
                sub_params = get_intersecting_yaml(yaml_pt1[key], yaml_pt2[key])
                if len(sub_params) > 0:
                    final[key] = sub_params
    return final

def safe_update_yaml_component(output_yaml_part, new_yaml_part, type_name):
    conflicts = []

    ignore_fields = ["description", "required", "annotations"]

    for key in new_yaml_part:
        if key in output_yaml_part:
            if new_yaml_part[key] != output_yaml_part[key]:
                conflict_fields = get_differing_fields(new_yaml_part[key], output_yaml_part[key])
                intersecting_yaml = get_intersecting_yaml(new_yaml_part[key], output_yaml_part[key])

                if "permissible_values" in conflict_fields:
                    if get_differing_fields(new_yaml_part[key]["permissible_values"], output_yaml_part[key]["permissible_values"]) == ['null']:
                        intersecting_yaml["permissible_values"]["null"] = None
                        conflict_fields.remove("permissible_values")
                        print.warning(f"Warning: Keeping value 'null' in permissible_values for {type_name} '{key}' (only sometimes present in input)")

                if not all([field in ignore_fields for field in conflict_fields]):
                    conflicts.append(key)
                    print(f"**\n"
                                    f"** Error: Conflicting {type_name} '{key}'. Same {type_name} was already found with different content (only 'final' is kept):\n"
                                    f"**   Existing: {new_yaml_part[key]}\n"
                                    f"**   New:      {output_yaml_part[key]}\n"
                                    f"**   Final:    {intersecting_yaml}\n"
                                    f"**")
                elif len(conflict_fields) > 0:
                    print(f"Warning: Removing fields {conflict_fields} from {type_name} '{key}' due to conflicting values.")

                output_yaml_part[key] = intersecting_yaml
        else:
            output_yaml_part[key] = new_yaml_part[key]
    return conflicts


def safe_update_yaml(output_yaml, keyword_yaml, conflicts):
    if "classes" in keyword_yaml:
        class_conflicts = safe_update_yaml_component(output_yaml["classes"], keyword_yaml["classes"], type_name="class")
        conflicts["class_conflicts"] += class_conflicts

    if "slots" in keyword_yaml:
        slot_conflicts = safe_update_yaml_component(output_yaml["slots"], keyword_yaml["slots"], type_name="slot")
        conflicts["slot_conflicts"] += slot_conflicts

    if "enums" in keyword_yaml:
        enum_conflicts = safe_update_yaml_component(output_yaml["enums"], keyword_yaml["enums"], type_name="enum")
        conflicts["enum_conflicts"] += enum_conflicts

class LinkMLDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        # Custom LinkMLDumper ensures lists are always indented (this is non-default behavior specific to LinkML format)
        return super(LinkMLDumper, self).increase_indent(flow, False)

    def write_line_break(self, data=None):
        super().write_line_break(data)

        if len(self.indents) == 1:
            super().write_line_break()

def write_yaml_output(yaml_output_dict, yaml_outfile):
    # This line ensures None values (as in {"key1": None, "key2": None}) do not show up as 'null' in YAML output
    # This is specific to LinkML format, not valid standard YAML format
    # it ensures enum values are formatted as follows:
    # permissible_values:
    #   key1:
    #   key2:
    yaml.add_representer(type(None),
                         representer=lambda self, _: self.represent_scalar('tag:yaml.org,2002:null', ''))

    with open(yaml_outfile, "w") as file:
        yaml.dump(yaml_output_dict, file, sort_keys=False, width=float("inf"), default_flow_style=False,
                  Dumper=LinkMLDumper, explicit_start=True)


def initialize_output_schema(schema_id, schema_name, schema_title):
    return {
        "id": schema_id,
        "name": schema_name,
        "title": schema_title,
        "description": f"LinkML representation of AIRR Standards for VDJServer data modeling.",
        "prefixes": {
            "linkml": "https://w3id.org/linkml/"
        },
        "default_range": "string",
        "imports": ["linkml:types"],
        "classes": {
            "AIRRStandards": {
                "abstract": True,
                "description": (
                    "An object directly converted from the AIRR schema."
                )
            }
        },

        "slots": {},
        "enums": {}
    }

def main(parsed_args):
    airr_yaml = get_airr_yaml(parsed_args.airr_schema_yaml)
    airr_version = airr_yaml["Info"]["version"]
    print("="*100)
    print("Converting airr schema to LinkML")
    print(f"Version: {airr_version}")


    # output_yaml = {
    #     "id": "https://github.com/vdjserver/vdjserver-airr-schema",
    #     "name": "vdjserver-airr-schema",
    #     "title": "VDJServer AIRR Schema",
    #     "description": f"LinkML representation of AIRR Standards {airr_version} for VDJServer data modeling.",
    #     "prefixes": {
    #             "vdjserver_airr_schema": "https://github.com/vdjserver/vdjserver-airr-schema/",
    #             "linkml": "https://w3id.org/linkml/",
    #         },
    #     "default_range": "string",   
    #     "imports": ["linkml:types"],   
    #     "classes": {},
    #     "slots": {},
    #     "enums": {},
    #     }

    schema_id  = "https://github.com/vdjserver/vdjserver-airr-schema"
    schema_name = "airr-schema"
    schema_title = "AIRR Standards Schema"
    output_yaml = initialize_output_schema(schema_id, schema_name, schema_title)

    internal_conflicts = {"class_conflicts": [],
                          "slot_conflicts": [],
                          "enum_conflicts": []}

    skip_keywords = ["Info", "Ontology", "CURIEMap", "InformationProvider", "Attributes", "FileObject", "DataSet",
                                          "Manifest", "DataFile", "InfoObject"]

    # skip_keywords = []
    # Simple keyworks:  add classes, slots and enums
    simple_keywords = get_simple_keywords_to_process(airr_yaml, skip_keywords)
    for keyword in simple_keywords:
        keyword_yaml = get_yaml_output_for_keyword(airr_yaml, keyword, parsed_args.superclass)
        safe_update_yaml(output_yaml, keyword_yaml, internal_conflicts)

    composition_keywords = get_composition_keywords_to_process(airr_yaml, skip_keywords)
    for keyword in composition_keywords:
        composition_yaml = get_yaml_output_for_composition_keyword(airr_yaml, output_yaml, keyword, parsed_args.superclass)
        safe_update_yaml(output_yaml, composition_yaml, internal_conflicts)

    write_yaml_output(output_yaml, parsed_args.output_file)

    print("="*100)


if __name__ == "__main__":
    parsed_args = get_arguments()

    main(parsed_args)

#Need to update output_yaml file.