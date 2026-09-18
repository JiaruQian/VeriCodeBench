# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import re
import pandas as pd
from jload import jload
import os


def get_error_str(code: str, errors: list, error_thres: bool) -> str:
    err_str = ""
    code_lines = code.split("\n")
    error_num_thres = 8 if error_thres else len(errors)

    for i, error in enumerate(errors[:error_num_thres]):
        start_line = error["pos"]["line"] - 1
        start_col = error["pos"]["column"]

        if error["endPos"] is None:
            end_line = start_line
            end_col = len(code_lines[start_line])
        else:
            end_line = error["endPos"]["line"] - 1
            end_col = error["endPos"]["column"]

        err_str += f"\nError {i + 1}:\n"
        err_str += "\nCorresponding Code:\n```lean4\n"

        error_code = ""
        for ii in range(-4, 0):
            if start_line + ii >= 0:
                error_code += f"{code_lines[start_line + ii]}\n"
        if start_line != end_line:
            error_code += (
                code_lines[start_line][:start_col]
                + "<error>"
                + code_lines[start_line][start_col:]
                + "\n"
            )

            if not error_thres:
                for j in range(start_line + 1, end_line):
                    error_code += f"{code_lines[j]}\n"
            else:
                show_line = 6
                for j in range(start_line + 1, min(end_line, start_line + show_line)):
                    error_code += f"{code_lines[j]}\n"
                if end_line > start_line + show_line:
                    leading_spaces = len(code_lines[j]) - len(code_lines[j].lstrip(" "))
                    error_code += (
                        "\n" + " " * leading_spaces + "... --[Truncated]-- ...\n"
                    )

            error_code += (
                code_lines[end_line][:end_col]
                + "</error>"
                + code_lines[end_line][end_col:]
                + "\n"
            )
        else:
            error_code += (
                code_lines[start_line][:start_col]
                + "<error>"
                + code_lines[start_line][start_col:end_col]
                + "</error>"
                + code_lines[start_line][end_col:]
                + "\n"
            )
        if end_line + 1 < len(code_lines):
            error_code += f"{code_lines[end_line + 1]}\n"

        err_str += error_code
        err_str += "\n```\n"
        err_str += f"\nError Message: {error['data']}\n"

    if len(errors) > error_num_thres:
        err_str += f"\n... [Omitted {len(errors) - error_num_thres} more errors] ...\n"

    return err_str


def extract_dpsk_instruction(dpsk: str) -> str:  # dpsk 7b output
    return dpsk.split("<｜User｜>")[1].split("<｜Assistant｜>")[0]


def extract_qwen_instruction(qwen: str) -> str:  # qwen output
    return qwen.split("<|im_start|>user")[1].split("<|im_end|>")[0].strip()


def load_data_for_correction(
    base_output_dir_for_prev_round: str,
    current_correction_round_num: int,
    num_samples_per_problem: int,
    base_output_template: str,
) -> list[dict]:
    print(
        f"Loading data for correction round {current_correction_round_num} from base directory: {base_output_dir_for_prev_round}"
    )

    if current_correction_round_num == 1:
        prev_round_suffix = ""  # R0 files have no suffix
    elif current_correction_round_num > 1:
        prev_round_suffix = f"_corr{current_correction_round_num - 1}"
    else:
        print(
            "Error: load_data_for_correction called with invalid current_correction_round_num (must be >= 1)."
        )
        return []

    prev_inference_file = os.path.join(
        base_output_dir_for_prev_round, f"to_inference_codes{prev_round_suffix}.json"
    )
    prev_compilation_file = os.path.join(
        base_output_dir_for_prev_round, f"code_compilation_repl{prev_round_suffix}.json"
    )

    assert prev_inference_file, (
        f"Error: Required previous inference file not found: {prev_inference_file}"
    )
    assert prev_compilation_file, (
        f"Error: Required previous compilation file not found: {prev_compilation_file}"
    )

    to_inference_data_prev_round = jload(prev_inference_file)
    compilation_results_data_prev_round = jload(prev_compilation_file)

    if base_output_template == "qwen":
        extract_fun = extract_qwen_instruction
    elif base_output_template == "dpsk":
        extract_fun = extract_dpsk_instruction
    else:
        print("unsupported base template")
        raise Exception

    if "messages_history_list" not in to_inference_data_prev_round[0]:
        for d in to_inference_data_prev_round:
            d["messages_history_list"] = [
                {"role": "user", "content": extract_fun(d["model_input"])}
            ]

    comp_lookup = {
        r["name"]: {"result": r["compilation_result"], "code": r["code"]}
        for r in compilation_results_data_prev_round
        if isinstance(r, dict)
        and "name" in r
        and "compilation_result" in r
        and "code" in r
    }

    passed_original_ids = set()
    failed_problem_variants = {}
    for item_prev_round in to_inference_data_prev_round:
        problem_id_variant = item_prev_round.get("problem_id")
        original_problem_id = item_prev_round.get("origin_problem_id")

        if not problem_id_variant or not original_problem_id:
            continue
        id_maps = item_prev_round.get("id_maps")
        if id_maps is None:
            assert current_correction_round_num == 1, (
                "Only first revision round accepts no id maps input. Please check your input data."
            )
            id_maps = [
                {"origin_problem_id": original_problem_id},
                {"generation_id": problem_id_variant},
            ]
        # if original_problem_id in passed_original_ids: continue

        if problem_id_variant in comp_lookup:
            comp_data = comp_lookup[problem_id_variant]

            if "errors" not in comp_data["result"]:
                continue

            is_pass = comp_data["result"].get("pass", False)
            is_complete = comp_data["result"].get("complete", False)

            if is_pass and is_complete:
                passed_original_ids.add(original_problem_id)
            else:
                if original_problem_id not in failed_problem_variants:
                    failed_problem_variants[original_problem_id] = []

                failed_problem_variants[original_problem_id].append(
                    {
                        "last_problem_id": problem_id_variant,
                        "origin_problem_id": original_problem_id,
                        "id_maps": id_maps,
                        "lean4_code": item_prev_round["lean4_code"],
                        "compiled_code_that_failed_in_prev_round": comp_data["code"],
                        "errors_for_compiled_code_from_prev_round": comp_data["result"],
                        "prev_round_llm_raw_output_for_new_prompt": item_prev_round.get(
                            "model_output", ""
                        ),
                        "history_messages_from_prev_round_for_new_prompt": item_prev_round.get(
                            "messages_history_list", []
                        ),
                    }
                )

    data_for_new_correction_attempts = []
    total_variants = 0
    unique_p = 0
    for original_id, variants in failed_problem_variants.items():
        if original_id in passed_original_ids:
            continue
        unique_p += 1
        total_variants += len(variants)
        for variant_idx, variant_item in enumerate(variants):
            for i in range(num_samples_per_problem):
                new_attempt_item = variant_item.copy()
                problem_id_variant = variant_item["last_problem_id"]
                new_attempt_item["problem_id"] = (
                    f"{problem_id_variant}_corr{current_correction_round_num}_g{i}"
                )
                new_attempt_item["id_maps"] = new_attempt_item["id_maps"].copy() + [
                    {
                        f"corr{current_correction_round_num}_id": new_attempt_item[
                            "problem_id"
                        ]
                    }
                ]
                data_for_new_correction_attempts.append(new_attempt_item)

    print(
        f"Correction Round {current_correction_round_num}: Identified {unique_p} unique problems with {total_variants} failed variants. "
        f"Generating {len(data_for_new_correction_attempts)} new samples for LLM inference."
    )
    return data_for_new_correction_attempts


def remove_comments(text: str) -> str:
    # First remove all /- ... -/ blocks
    text = re.sub(r"/-.*?-/", "", text, flags=re.DOTALL)
    # Then remove -- comments from each line
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Split on -- and keep only the first part
        cleaned_line = line.split("--", 1)[0]
        cleaned_lines.append(cleaned_line)
    # Join back together and remove excessive empty lines
    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text.strip()


def return_theorem_to_prove(text: str) -> str | None:
    # Pattern that matches from 'theorem' or 'lemma' to ':= by sorry' with any content in between
    pattern = r"((?:theorem).*?:=\s*by\s*sorry)"
    match = re.search(pattern, text, re.DOTALL)
    return match.span() if match else None


def return_theorem_to_replace(text: str) -> str | None:
    # Pattern that matches from 'theorem' to ':= by sorry' with any content in between
    pattern = r"((?:^|\s)theorem\s+.*?:=\s*by)"
    match = re.search(pattern, text, re.DOTALL)
    return match.span() if match else None


def replace_statement_in_proof(statement: str, proof: str) -> str:
    if ("apply?" in proof) or ("exact?" in proof):
        return "**Error**, 'apply?' or 'exact?' is used, which is not allowed."
    stats_re = remove_comments(statement)
    stats_span_ = return_theorem_to_prove(stats_re)
    if stats_span_ is None:
        error_app = "\n".join(["\n"] + ["-- " + x for x in statement.split("\n")])
        return f"**Error**, can not find 'theorem' and ':= sorry' in {error_app}"
    proof_str = remove_comments(proof)
    span = return_theorem_to_replace(proof_str)
    if span is None:
        error_app = "\n".join(["\n"] + ["-- " + x for x in proof.split("\n")])
        return f"**Error**, can not find 'theorem' and ':=' in {error_app}"
    return stats_re[: stats_span_[1]].replace("sorry", "") + proof_str[span[1] :]


class InferenceHandler:
    def extract_code(self, inputs: str) -> str | None:
        pattern = r"```lean4\n(.*?)\n```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return matches[-1]
        pattern = r"```lean4\n(.*?)```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return matches[-1]
        pattern = r"```lean\n(.*?)```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return matches[-1]
        return None

    def clean_code_string(self, code_string: str) -> str:
        # Split the code string into lines
        lines = code_string.splitlines()

        # Filter out lines that start with specified keywords or are blank
        filtered_lines = [
            line
            for line in lines
            if not (
                line.startswith("import")
                or line.startswith("set_option")
                or line.startswith("open")
                or line.strip() == ""
            )
        ]

        # Join the remaining lines back into a single string
        return "\n".join(filtered_lines)

    def prover_dialog(self, lean4_code: str) -> list[dict]:
        raise NotImplementedError

    def prover_prompt(self, lean4_code: str) -> str:
        raise NotImplementedError

    def generate_correction_dialog(
        self,
        history_messages_from_prev_round: list[dict],
        prev_round_llm_raw_output: str,
        error_message_for_prev_round: str,
        current_correction_round_num: int,
    ) -> list[dict]:
        raise NotImplementedError

    def generate_correction_prompt(
        self,
        history_messages_from_prev_round: list[dict],
        prev_round_llm_raw_output: str,
        error_message_for_prev_round: str,
        current_correction_round_num: int,
    ) -> str:
        raise NotImplementedError

    def split_list_into_chunks(self, input_list: list, num_chunks: int) -> list[list]:
        """Split a list into approximately equal-sized chunks using only Python built-ins."""
        # Make sure input_list is a regular Python list
        input_list = list(input_list)

        # Calculate the length of the list
        list_length = len(input_list)

        # Calculate the base size for each chunk
        base_chunk_size = list_length // num_chunks

        # Calculate how many chunks need an extra element
        # (when the list can't be evenly divided)
        remainder = list_length % num_chunks

        chunks = []
        index = 0

        # Create each chunk
        for i in range(num_chunks):
            # Determine this chunk's size (add an extra element if needed)
            current_chunk_size = base_chunk_size + (1 if i < remainder else 0)

            # If we've reached the end of the list or this chunk would be empty, stop
            if index >= list_length or current_chunk_size == 0:
                break

            # Add this chunk to our result
            chunks.append(input_list[index : index + current_chunk_size])
            index += current_chunk_size

        return chunks

    def load_split(self, input_file: str, split: str) -> list[dict]:
        df = pd.read_json(input_file, lines=True)
        if split == "none":
            return df.to_dict(orient="records")
        else:
            return df[df.split.apply(lambda x: str(x) == str(split))].to_dict(
                orient="records"
            )

    def problem_check(self, statement: str, full_code: str) -> str:
        return full_code


class DeepSeekCoTHandler(InferenceHandler):
    def extract_code(self, inputs: str) -> str | None:
        import_head = "import Mathlib\nimport Aesop\n\nset_option maxHeartbeats 0\n\nopen BigOperators Real Nat Topology Rat\n\n"
        pattern = r"```lean4\n(.*?)\n```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return import_head + matches[-1]
        pattern = r"```lean4\n(.*?)```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return import_head + matches[-1]
        pattern = r"```lean\n(.*?)```"
        matches = re.findall(pattern, inputs, re.DOTALL)
        if matches:
            return import_head + matches[-1]
        return None

    def prover_dialog(self, lean4_code: str) -> list[dict]:
        formal_statement = (
            lean4_code.split(":= by")[0] + ":= by sorry"
        )  # include sorry https://huggingface.co/deepseek-ai/DeepSeek-Prover-V2-7B
        prompt = f"Complete the following Lean 4 code:\n\n```lean4\n{formal_statement}```\n\nBefore producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.\nThe plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof."
        messages = [{"role": "user", "content": prompt}]
        return messages

    def problem_check(self, statement: str, full_code: str) -> str:
        return replace_statement_in_proof(statement, full_code)

    def generate_correction_dialog(
        self,
        history_messages_from_prev_round: list[dict],
        prev_round_llm_raw_output: str,
        error_message_for_prev_round: str,
        current_correction_round_num: int,
    ):
        current_messages = list(history_messages_from_prev_round)

        # Add PREVIOUS assistant's (failed) attempt
        assistant_content = prev_round_llm_raw_output
        current_messages.append({"role": "assistant", "content": assistant_content})

        # Add CURRENT user feedback and request for new attempt
        user_feedback_content = (
            f"The proof (Round {current_correction_round_num - 1}) is not correct. Following is the compilation error message, where we use <error></error> to signal the position of the error.\n\n{error_message_for_prev_round}"
            "\n\nBefore producing the Lean 4 code to formally prove the given theorem, provide a detailed analysis of the error message."
        )
        current_messages.append({"role": "user", "content": user_feedback_content})
        return current_messages


class DeepSeekNonCoTHandler(InferenceHandler):
    def prover_prompt(self, lean4_code: str) -> str:
        formal_statement = (
            lean4_code.split(":= by")[0] + ":= by"
        )  # don't include sorry, directly completion
        return f"Complete the following Lean 4 code:\n\n```lean4\n{formal_statement}"

    def generate_correction_prompt(
        self,
        history_messages_from_prev_round: list[dict],  # Not used by non-chat
        prev_round_llm_raw_output: str,  # Not used by non-chat directly in prompt
        error_message_for_prev_round: str,
        current_correction_round_num: int,
    ) -> str:
        commented_errors = "\n".join(
            [
                f"-- {line}"
                for line in error_message_for_prev_round.splitlines()
                if line.strip()
            ]
        )

        prompt_str = (
            f"-- The previous proof attempt (Round {current_correction_round_num - 1}) resulted in compilation errors:\n"
            f"{commented_errors}\n"
            f"-- Please provide a corrected version. Wrap the proof in ```lean4 and ```."
        )
        return prompt_str


class KiminaCoTHandler(InferenceHandler):
    def prover_dialog(self, lean4_code: str) -> list[dict]:
        formal_statement = lean4_code.split(":= by")[0] + ":= by"
        # don't include sorry https://huggingface.co/AI-MO/Kimina-Prover-Preview-Distill-7B
        problem = self.clean_code_string(formal_statement)
        prompt = "Think about and solve the following problem step by step in Lean 4."
        prompt += f"\n# Problem:{problem}"
        prompt += f"\n# Formal statement:\n```lean4\n{formal_statement}\n```\n"

        return [
            {
                "role": "system",
                "content": "You are an expert in mathematics and Lean 4.",
            },
            {"role": "user", "content": prompt},
        ]

    def generate_correction_dialog(
        self,
        history_messages_from_prev_round: list[dict],
        prev_round_llm_raw_output: str,
        error_message_for_prev_round: str,
        current_correction_round_num: int,
    ) -> list[dict]:
        current_messages = []

        current_messages = list(history_messages_from_prev_round)

        assistant_content = prev_round_llm_raw_output

        current_messages.append({"role": "assistant", "content": assistant_content})

        user_feedback_content = (
            f"The proof (Round {current_correction_round_num - 1}) is not correct. Following is the compilation error message, where we use <error></error> to signal the position of the error.\n\n{error_message_for_prev_round}"
            "\n\nBefore producing the Lean 4 code to formally prove the given theorem, provide a detailed analysis of the error message."
        )
        current_messages.append({"role": "user", "content": user_feedback_content})
        return current_messages

    def problem_check(self, statement: str, full_code: str) -> str:
        return replace_statement_in_proof(statement, full_code)
