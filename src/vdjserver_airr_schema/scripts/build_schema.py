# Load AIRR schema.
# Load VDJServer schema.
# Identify AIRR references.
# Identify VDJServer classes.
# Produce a preliminary LinkML structure.
# Write it to vdjserver_airr_schema.yaml.

from pathlib import Path
import yaml
import json
import argparse


def get_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description="Script to convert AIRR openapi3 schema to LinkML")

    parser.add_argument("-a", "--airr_schema", type=str, help="Input openapi3 YAML file",
                        default="../../airr_schema/airr-standards-v2.0/specs/airr-schema-openapi3.yaml")
    parser.add_argument("-v", "--vdjserver_schema", type=str, help="VDJServer Source Schema",
                            default="../../vdjserver_airr_schema/schema/vdjserver_schema_source.yaml")

    return parser.parse_args()


def load_yaml(path: str | Path) -> dict:
    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_definitions(schema: dict) -> dict:
    # VDJServer schema format:
    # top-level objects are schema definitions
    definitions = {
        key: value
        for key, value in schema.items()
        if isinstance(value, dict)
    }

    if definitions:
        return definitions

    raise ValueError("Could not find schema definitions")

def find_airr_refs(obj):
    refs = []
    refs_other = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "$ref" and isinstance(value, str):
                if "airr-community/airr-standards" in value:
                    refs.append(value)
                else:
                    refs_other.append(value)
                    print(refs_other)


            refs.extend(find_airr_refs(value))

    elif isinstance(obj, list):
        for item in obj:
            refs.extend(find_airr_refs(item))

    return refs

def main(parsed_args):
    airr_schema = load_yaml(parsed_args.airr_schema)

    vdjserver_schema = load_yaml( parsed_args.vdjserver_schema)

    airr_definitions = get_definitions(airr_schema)
    vdjserver_definitions = get_definitions(vdjserver_schema)


    print(f"AIRR classes: {len(airr_definitions)}")
    print(f"VDJServer classes: {len(vdjserver_definitions)}")

    for class_name, class_schema in vdjserver_definitions.items():
        refs = find_airr_refs(class_schema)

        if refs:
            print(class_name)
            for ref in refs:
                print("   ", ref)


    # print("AIRR classes:")
    # for name in airr_definitions:
    #     print(f"  {name}")

    # print("\nVDJServer classes:")
    # for name in vdjserver_definitions:
    #     print(f"  {name}")
        

    # for name in ["Study", "Repertoire", "Subject"]:
    #     print("\n" + "=" * 80)
    #     print(name)
    #     print("=" * 80)
    #     print(json.dumps(airr_definitions[name], indent = 4))


if __name__ == "__main__":
    parsed_args = get_arguments()

    main(parsed_args)









