# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import fire


def get_label(d: dict) -> str:
    """
    Get the function name of a CLEVER task.
    """
    # "function_signature": "def string_xor(a: str, b: str) -> str",
    # extract the function name:
    sig = d["function_signature"]
    return sig.split("(")[0].split(" ")[1]


def main(input_path, output_path):
    with (
        open(input_path, "r") as f_in,
        open(output_path, "w") as f_out,
    ):
        for i, line in enumerate(f_in):
            d = json.loads(line)
            d["id"] = f"clever:{i}"
            d["function_name"] = get_label(d)
            output_line = json.dumps(d)
            f_out.write(output_line + "\n")


if __name__ == "__main__":
    fire.Fire(main)
