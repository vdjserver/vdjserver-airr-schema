import argparse
import yaml
import sys
import logging
import glob
from datetime import datetime
import json
import re


def get_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description="Script to convert AIRR openapi3 schema to LinkML")

    parser.add_argument("-a", "--source_schema", type=str, help="VDJServer openapi3 YAML file",
                        default="../../vdjserver_airr_schema/schema/vdjserver_schema_source.yaml")
    parser.add_argument("-o", "--output_file", type=str, help="Output file to write the LinkML to",
                            default="../../vdjserver_airr_schema/schema/vdjserver_schema.yaml")
    parser.add_argument("-s", "--superclass",  type=str, help="Superclass name (will be referenced for each class under 'is_a')", default="VDJServerStandards")

    return parser.parse_args()

def get_airr_yaml(file_location):
    with open(file_location) as file:
        airr_yaml = yaml.safe_load(file)
    return airr_yaml

def empty_yaml_output():
    return{
        "classes": {},
        "slots": {},
        "enums": {}
    }

def merge_yaml_output(output, new_output):
    output["classes"].update(new_output.get("classes", {}))
    output["slots"].update(new_output.get("slots", {}))
    output["enums"].update(new_output.get("enums", {}))

class LinkMLDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        # Custom LinkMLDumper ensures lists are always indented (this is non-default behavior specific to LinkML format)
        return super(LinkMLDumper, self).increase_indent(flow, False)

    def write_line_break(self, data=None):
        super().write_line_break(data)

        if len(self.indents) == 1:
            super().write_line_break()


def write_yaml_output(yaml_output_dict, yaml_outfile):
    yaml.add_representer(type(None),
                         representer=lambda self, _: self.represent_scalar('tag:yaml.org,2002:null', ''))

    with open(yaml_outfile, "w") as file:
        yaml.dump(yaml_output_dict, file, sort_keys=False, width=float("inf"), default_flow_style=False,
                  Dumper=LinkMLDumper, explicit_start=True)

def get_keywords_to_process(source_yaml, skip_keywords):
    independent_keywords = []
    dependent_keywords = []

    for key, value in source_yaml.items():
        if key in skip_keywords:
            continue

        # Normal class: no allOf / anyOf
        if "type" in value and "allOf" not in value and "anyOf" not in value:
            independent_keywords.append(key)
            continue

        # Classes using allOf
        if "allOf" in value:
            has_local_ref = any("$ref" in item and item["$ref"] for item in value["allOf"])

            if has_local_ref:
                dependent_keywords.append(key)
            else:
                independent_keywords.append(key)

    return independent_keywords, dependent_keywords

def snake_to_camel_case(word):
    new_word = ''.join('_' if x == '' else x.capitalize() for x in word.split('_'))
    return new_word

def get_inline_object_class(parent_class_name, slot_name, slot_yaml):
    "Convert an anonymous openAPI object with properties into a linkML class"
    inline_class_name = f"{snake_to_camel_case(slot_name)}Details"
    description = slot_yaml.get("description", f"Default {inline_class_name} description")

    inline_output = empty_yaml_output()

    class_slots = []

    for nested_slot_name, nested_slot_yaml in slot_yaml.get("properties", {}).items():
        slot, id_slot, nested_output = get_slot(nested_slot_name, nested_slot_yaml, inline_class_name)
        class_slots.append(nested_slot_name)
        merge_yaml_output(inline_output, nested_output)
    # Add the inline class itself
    inline_output["classes"][inline_class_name] = {
        "description": description,
        "slots": class_slots
    }

    return inline_class_name, inline_output

def get_slot_range(slot_name, slot_yaml, keyword):
    slot_type = slot_yaml.get("type")

    # ----------------------------------------
    # Array
    # ----------------------------------------
    if slot_type == "array":
        return get_slot_range(slot_name, slot_yaml["items"], keyword)
    
    # ----------------------------------------
    # Reference
    # ----------------------------------------
    if "$ref" in slot_yaml:
        ref = slot_yaml["$ref"]
        if ref.startswith("#/"):
            return ref[2:]
        print(f"ERROR: Unsupported $ref for slot {slot_name} : {ref}")
        return None
    
    # ----------------------------------------
    # Map / additionalProperties
    # ----------------------------------------
    if "additionalProperties" in slot_yaml:
        additional_properties = slot_yaml["additionalProperties"]
        if isinstance(additional_properties, dict):
            return get_slot_range(slot_name, additional_properties, keyword)
        
    # ----------------------------------------
    # Enum
    # ----------------------------------------
    if "enum" in slot_yaml:
        return f"{keyword}{snake_to_camel_case(slot_name)}Enum"
    
    # ----------------------------------------
    # String
    # ----------------------------------------
    if slot_type == "string":
        fmt = slot_yaml.get("format")
        if fmt == "date":
            return "date"
        elif fmt == "date-time":
            return "datetime"
        else:
            return "string"
        
    # ----------------------------------------
    # Integer / Boolean
    # ----------------------------------------
    if slot_type in ["integer", "boolean"]:
        return slot_type
    
    # ----------------------------------------
    # Number
    # ----------------------------------------
    if slot_type == "number":
        return "float"
    
    # ----------------------------------------
    # anyOf
    # ----------------------------------------
    if "anyOf" in slot_yaml:
        for option in slot_yaml["anyOf"]:
            option_type = option.get("type")
            
            if option_type =="array":
                return get_slot_range(slot_name, option["items"], keyword)
            elif option_type in ["string", "integer", "boolean", "number"]:
                return get_slot_range(slot_name, option, keyword)
            
            print(f" Error: Cannot determine range for slot: ({slot_name}) omitting range.")
            return None
    # ----------------------------------------
    # Object
    # ----------------------------------------
    if slot_type == "object":
        print(f"Cannot determine range for object slot ({slot_name}); no properties found.")
        return None
    # ----------------------------------------
    # Unknown
    # ----------------------------------------
    if slot_type is None:
        print(f"Error: No slot type found for ({slot_name}); omitting range.")
        return None

    print(f"Not implemented slot_type: {slot_type}")
    raise NotImplementedError(slot_yaml)

def is_multivalued(slot_yaml):

    if slot_yaml.get("type") == "array":
        return True
    
    if "anyOf" in slot_yaml:
        return any(option.get("type") == "array" for option in slot_yaml["anyOf"])
    
    return False
    

def get_slot_annotation(slot_yaml):
    annotations = dict()

    if "nullable" in slot_yaml:
        annotations["nullable"] = slot_yaml["nullable"]

    if "x-vdjserver" in slot_yaml:
        if "nullable" in slot_yaml["x-vdjserver"]:
            assert "nullable" not in annotations or annotations["nullable"] == slot_yaml["x-vdjserver"]["nullable"], \
                f"Found contradicting values for nullable in: {slot_yaml}"
            annotations["nullable"] = slot_yaml["x-vdjserver"]["nullable"]

    return annotations

def normalize_slot_name(name):
    # camelCase → snake_case
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', name)
    return name.lower()

def get_slot(slot_name, slot_yaml, keyword):
    identifier_slot = None
    description = slot_yaml.get("description", "Default slot description").strip()
    slot = {
        slot_name: {
            "name": slot_name,
            "description": description
        }
    }

    nested_output = empty_yaml_output()
    
    # --------------------------------------------------
    # Resolve enum
    # -------------------------------------------------
    # if "enum" in slot_yaml:
    #     enum_name = get_slot_range(slot_name, slot_yaml, keyword)
    #     nested_output["enums"][enum_name] = {
    #         "permissible_values": {
    #             value: {} for value in slot_yaml["enum"]
    #         }
    #     }
    #     slot[slot_name]["range"] = enum_name

    # --------------------------------------------------
    # Object with additionalProperties = map/dictionary
    # -------------------------------------------------
    additionalProperties = slot_yaml.get("additionalProperties")
    if isinstance(additionalProperties, dict):
        value_range = get_slot_range(slot_name, additionalProperties, keyword)
        if value_range:
            slot[slot_name]["range"] = value_range
        # This is a map, not an inline object
        slot[slot_name]["inlined"] = True
        slot[slot_name]["inlined_as_list"] = True

    elif slot_yaml.get("type") == "object":
        inline_class_name, inline_output = get_inline_object_class(keyword, slot_name, slot_yaml)
        slot[slot_name]["range"] = inline_class_name
        # Bring the nested class/slots/enums into our result
        merge_yaml_output(nested_output, inline_output)

    # --------------------------------------------------
    # Normal scalar/array/ref/etc.
    # --------------------------------------------------
    else:
        slot_range = get_slot_range(slot_name, slot_yaml, keyword)

        if slot_range:
            slot[slot_name]["range"] = slot_range

            if "enum" in slot_yaml:
                nested_output["enums"][slot_range] = {
                    "permissible_values": {
                        value : {} for value in slot_yaml["enum"]
                    }
                }

        if is_multivalued(slot_yaml):
            slot[slot_name]["multivalued"] = True

        annotations = get_slot_annotation(slot_yaml)

        if len(annotations):
            slot[slot_name]["annotations"] = annotations
    # add the current slot
    nested_output["slots"].update(slot)
    return slot, identifier_slot, nested_output

def get_all_slots(source_yaml, keyword):
    output = empty_yaml_output()
    identifier_slot = None

    if "properties" in source_yaml[keyword]:
        for slot_name, slot_yaml in source_yaml[keyword]["properties"].items():
            slot, id_slot, nested_output = get_slot(slot_name, slot_yaml, keyword)
            # Add the slot/class/enum information discovered
            # while processing this slot.
            merge_yaml_output(output, nested_output)
            if id_slot:
                if identifier_slot:
                    raise ValueError(
                        f"Multiple class identifiers found for {keyword}"
                    )
                identifier_slot = id_slot

    return output, identifier_slot

    
def get_enum(base_name, slot_yaml, keyword):
    if slot_yaml.get("type") == "array":
        return get_enum(base_name, slot_yaml["items"], keyword)
    
    if "$ref" in slot_yaml:
        ref = slot_yaml["$ref"]
        print(f"Ref enum. Check. {ref}")
        return None
    elif "enum" in slot_yaml:
        closed_vocabulary_enum = {
            # "name": f"{keyword}{base_name}Enum",
            "name": f"{base_name}Enum",
            "permissible_values": {
                enum_val: None for enum_val in slot_yaml["enum"] if enum_val is not None
            }
        }
        return closed_vocabulary_enum
    
def get_all_enums(keyword_yaml, keyword):
    all_enums = {}
    if "properties" in keyword_yaml:
        for slot_name, slot_yaml in keyword_yaml["properties"].items():
            base_name = snake_to_camel_case(slot_name)
            if base_name == "Property":
                pass
            new_enum = get_enum(base_name, slot_yaml, keyword)
            if new_enum:
                all_enums[new_enum["name"]] = new_enum
    return all_enums


def get_yaml_output_for_keyword(source_yaml, keyword, linkml_superclass):
    output, identifier_slot = get_all_slots(source_yaml, keyword)
    class_name = keyword
    required_slots = source_yaml[keyword].get("required", [])
    description = source_yaml[keyword].get("description", f"Default {class_name} description")
    # The slots directly defined by this class
    class_slots = list(source_yaml[keyword].get("properties", {}).keys())
    class_def = {
        "is_a": linkml_superclass,
        "description": description,
        "slots": class_slots
    }
     # Handle required slots
    if required_slots:
        class_def["slot_usage"] = {}
        for slot_name in required_slots:
            class_def["slot_usage"][slot_name] = {"required": True}
    if identifier_slot:
        if "slot_usage" not in class_def:
            class_def["slot_usage"] = {}
        class_def["slot_usage"][identifier_slot] = {
            "identifier" : True,
            "required": True
        }
    # Add the main class
    output["classes"][class_name] = class_def
    # print(json.dumps(output, indent = 4))
    return output


def get_differing_fields(yaml_pt1, yaml_pt2):
    differing_fields = []
    for key in yaml_pt1:
        if key not in yaml_pt2 or yaml_pt1[key] != yaml_pt2[key]:
            differing_fields.append(key)
    for key in yaml_pt2:
        if key not in yaml_pt1:
            differing_fields.append(key)
    
    return differing_fields

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


    
def get_slot_range_conflicts(output_yaml, new_slots, class_name):
    conflicts = {}

    for slot_name, new_slot in new_slots.items():
        if slot_name not in output_yaml["slots"]:
            continue
        existing_slot = output_yaml["slots"][slot_name]
        existing_range = existing_slot.get("range")
        new_range = new_slot.get("range")
        if existing_range and new_range and existing_range != new_range:
            conflicts[slot_name] = new_range
    return conflicts

# add ranges to slot usage
def add_range_to_slot_usage(class_def, range_conflicts):
    if not range_conflicts:
        return
    if "slot_usage" not in class_def:
        class_def["slot_usage"] = {}
    for slot_name, slot_range in range_conflicts.items():
        class_def["slot_usage"].setdefault(slot_name, {})
        class_def["slot_usage"][slot_name]["range"] = slot_range

def safe_update_yaml_component(output_yaml_part, new_yaml_part, type_name):
    conflicts = []
    ignore_fields = ["description", "required", "annotations"]
    
    for key in new_yaml_part:
        if key not in output_yaml_part:
            output_yaml_part[key] = new_yaml_part[key]
            continue
        if new_yaml_part[key] == output_yaml_part[key]:
            continue
        conflict_fields =  get_differing_fields(new_yaml_part[key], output_yaml_part[key])
        # --------------------------------------------------
        # Slot range conflicts are handled by slot_usage.
        # Do NOT merge them and do NOT remove the range.
        # --------------------------------------------------
        if type_name == "slot" and "range" in conflict_fields:
            other_conflicts = [field for field in conflict_fields if field != "range"]

            if not all(field in ignore_fields for field in other_conflicts):
                conflicts.append(key)
            continue

        intersecting_yaml = get_intersecting_yaml(new_yaml_part[key], output_yaml_part[key])

        if "permissible_values" in conflict_fields:
            if get_differing_fields( new_yaml_part[key]["permissible_values"], output_yaml_part[key]["permissible_values"]) == ["null"]:
                intersecting_yaml["permissible_values"]["null"] = None
                conflict_fields.remove("permissible_values")

                print(
                    f"Warning: Keeping value 'null' in permissible_values "
                    f"for {type_name} '{key}' "
                    f"(only sometimes present in input)"
                )

        if not all(field in ignore_fields for field in conflict_fields):
            conflicts.append(key)

            print(
                f"**\n"
                f"** Error: Conflicting {type_name} '{key}'. "
                f"Same {type_name} was already found with different content:\n"
                f"**   Existing: {output_yaml_part[key]}\n"
                f"**   New:      {new_yaml_part[key]}\n"
                f"**   Final:    {intersecting_yaml}\n"
                f"**"
            )

        elif len(conflict_fields) > 0:
            print(f"Warning: Removing fields {conflict_fields} from {type_name} '{key}' due to conflicting values.")

        output_yaml_part[key] = intersecting_yaml

    return conflicts

                
def safe_update_yaml(output_yaml, keyword_yaml, conflicts, class_name = None):
    if "classes" in keyword_yaml:
        class_conflicts = safe_update_yaml_component(output_yaml["classes"], keyword_yaml["classes"], type_name = "class")
        conflicts["class_conflicts"] += class_conflicts
    if "slots" in keyword_yaml:
        range_conflicts = {}
        if class_name:
            range_conflicts = get_slot_range_conflicts(output_yaml, keyword_yaml["slots"], class_name)
            class_def = keyword_yaml["classes"].get(class_name)
            if class_def:
                add_range_to_slot_usage(class_def, range_conflicts)

        slot_conflicts = safe_update_yaml_component(output_yaml["slots"], keyword_yaml["slots"], type_name = "slot")
        conflicts["slot_conflicts"] += slot_conflicts
    if "enums" in keyword_yaml:
        enum_conflicts = safe_update_yaml_component(output_yaml["enums"], keyword_yaml["enums"], type_name = "enum")
        conflicts["enum_conflicts"] += enum_conflicts
    
#Not using this yet. But need to
def get_superclass(ref, default):
    if "airr-schema-openapi3.yaml#/" in ref:
        return "AIRRStandards"
    
    if ref.startswith("#/"):
        return ref[2:]
    else:
        print(f"Returning default for $ref: {ref}")
        return default


def get_yaml_output_for_composition_keyword(source_yaml, output_yaml, keyword, linkml_superclass):
    class_name = keyword
    description = source_yaml[keyword].get("description", f"Default {class_name} description")

    composition_yaml = empty_yaml_output()
    class_def = {
        "is_a": linkml_superclass,
        "description": description,
        "slots": []
    }
    composition_yaml["classes"][class_name] = class_def
    identifier_slot = None
    # --------------------------------------------------
    # Process properties directly defined on the class
    # --------------------------------------------------
    direct_output, new_identifier = get_all_slots(source_yaml, keyword)
    merge_yaml_output(composition_yaml, direct_output)
    direct_slots = list(source_yaml[keyword].get("peoperties", {}).keys())
    composition_yaml["classes"][class_name]["slots"].extend(direct_slots)

    if new_identifier:
        identifier_slot = new_identifier

    # --------------------------------------------------
    # Process allOf
    # --------------------------------------------------

    for class_yaml in source_yaml[keyword].get("allOf", []):
        # ----------------------------------------------
        # $ref
        # ----------------------------------------------
        if "$ref" in class_yaml:
            ref = class_yaml["$ref"]
            super_class_name = get_superclass(ref, linkml_superclass)
            if super_class_name not in output_yaml["classes"]:
                print(
                    f"Warning: Local superclass '{super_class_name}' "
                        f"for '{class_name}' is not currently available."
                    )
            composition_yaml["classes"][class_name]["is_a"] = super_class_name
            continue
        # ----------------------------------------------
        # Inline allOf object
        # ----------------------------------------------
        inline_yaml = {keyword: class_yaml}
        allof_output, new_identifier = get_all_slots(inline_yaml, keyword)
        merge_yaml_output(composition_yaml, allof_output)
        # Add the slots defined by this allOf object
        all_of_slots = list(class_yaml.get("properties", {}).keys())

        for slot_name in all_of_slots:
            if slot_name not in composition_yaml["classes"][class_name]["slots"]:
                composition_yaml["classes"][class_name]["slots"].append(slot_name)
        if new_identifier:
            print(f"WARNING: Got another identifier in slot {slot_name} as {new_identifier}")
            identifier_slot = new_identifier

    # ----------------------------------------------
    # Required slots
    # ----------------------------------------------
    required_slots = source_yaml[keyword].get("required", [])
    if required_slots:
        if "slot_usage" not in composition_yaml["classes"][class_name]:
            composition_yaml["classes"][class_name]["slot_usage"] = {}
        for slot_name in required_slots:
            if slot_name not in composition_yaml["classes"][class_name]["slots"]:
                print( f"Warning: Required slot '{slot_name}' is not defined in class '{class_name}'.")
                continue

            composition_yaml["classes"][class_name]["slot_usage"][slot_name] = {"required": True}
    
    # ----------------------------------------------
    # Identifier
    # ----------------------------------------------
    if identifier_slot:
        if "slot_usage" not in composition_yaml["classes"][class_name]:
            composition_yaml["classes"][class_name]["slot_usage"] = {}
        composition_yaml["classes"][class_name]["slot_usage"][identifier_slot] = {
            "identifier": True,
            "required": True
        }
    return composition_yaml


def initialize_output_schema(schema_id, schema_name):
    return {
        "id": schema_id,
        "name": schema_name,
        "title": "VDJServer Schema",
        "description": f"LinkML representation of Schema definitions for VDJServer standards objects.",
        "prefixes": {
            "linkml": "https://w3id.org/linkml/"
        },
        "default_range": "string",
        "imports": ["linkml:types","airr_schema"],
        # "imports": ["linkml:types"],
        "classes": {
            "AIRRStandards": {
                "abstract": True,
                "description": (
                    "An object directly converted from the AIRR schema."
                )
            },
            "VDJServerStandards": {
                "abstract": True,
                "description": (
                    "An object directly converted from the VDJServer schema."
                )
            }
        },

        "slots": {},
        "enums": {}
    }


def main(parsed_args):
    source_yaml = get_airr_yaml(parsed_args.source_schema)
    source_version = source_yaml["Info"]["version"]
    print("="*100)
    print("Converting airr schema to LinkML")
    print(f"Version: {source_version}")
    schema_id  = "https://github.com/vdjserver/vdjserver-airr-schema"
    schema_name = "vdjserver-airr-schema"
    
    output_yaml = initialize_output_schema(schema_id, schema_name)
    
    internal_conflicts = {"class_conflicts": [],
                          "slot_conflicts": [],
                          "enum_conflicts": []}
    
    skip_keywords = ["Info","UserAccountCreation", "ErrorTelemetry", "ProjectPermissionRequest", "PublicFeedbackRequest", "VDJPipeInputs", "VDJPipeParameters", "PrestoInputs", "PrestoParameters" ,"TakaraBioUMIInputs", "TakaraBioUMIParameters",
                     "IgBlastInputs", "IgBlastParameters", "CellRangerInputs", "CellRangerParameters", "TILDEInputs", "TILDEParameters", "RepCalcInputs", "RepCalcParameters", "InfoObject",
                     ]
    # skip_keywords = []
    
    independent_keywords, dependent_keywords = get_keywords_to_process(source_yaml, skip_keywords)
    
    
    # independent_keywords = ["CommonExtension", "ProjectPermission" ]
    # independent_keywords = ["CommonExtension", "FilePostitRequest", "ProjectFile","ProjectJob"]
    # dependent_keywords = ["StudyExtension",  "Study", "ProjectExtension", "Project", "RepertoireExtension",]
    # independent_keywords = ["CommonExtension", "ProjectPermission",]
    # dependent_keywords = ["StudyExtension", "Study", "ProjectExtension", "Project", "RepertoireExtension", "AIRRRepertoire"]
    
    # Process simple classes first
    for keyword in independent_keywords:
        print("Keyword: ", keyword)
        # print(json.dumps(source_yaml[keyword], indent = 4))
        keyword_yaml = get_yaml_output_for_keyword(source_yaml, keyword, parsed_args.superclass)
        safe_update_yaml(output_yaml, keyword_yaml, internal_conflicts, class_name=keyword)
    print(json.dumps(keyword_yaml, indent = 4))

    for keyword in dependent_keywords:
        print("Composition keyword: ", keyword)
        composition_yaml = get_yaml_output_for_composition_keyword(source_yaml, output_yaml, keyword, parsed_args.superclass)
        safe_update_yaml(output_yaml, composition_yaml, internal_conflicts, class_name=keyword)


    # print("All Classes: \n", list(source_yaml.keys()))
    # print(f"Total number of Class in vdjserver Schema: {len(source_yaml.keys())}")
    
    # print("Total skipped classes: ", len(skip_keywords))
    # print("Simple classes: \n")
    # print(independent_keywords)
    # print(f"Total number of simple keywords: {len(independent_keywords)}")
    
    # print("Composition Classes: \n")
    # print(dependent_keywords)
    # print(f"Total number of composition_keywords keywords: {len(dependent_keywords)}")
    
    # print(json.dumps(source_yaml['AnalysisProperties'], indent = 4))
    # print(json.dumps(keyword_yaml, indent = 4))
    
    # print(output_yaml)
    
    write_yaml_output(output_yaml, parsed_args.output_file)

    print("="*100)



if __name__ == "__main__":
    parsed_args = get_arguments()

    main(parsed_args)