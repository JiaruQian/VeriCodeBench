# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import asyncio
from logging import getLogger
import fire
from src.utils import initialize_logger


from langchain_google_genai import ChatGoogleGenerativeAI


logger = getLogger()


LLM = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)


async def llm_call(
    LLM,
    d: dict,
    prompt_template: str,
    output_field: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        prompt = prompt_template.format(**d)
        dialog = [{"role": "user", "content": prompt}]
        response = (await LLM.ainvoke(dialog)).content
        if isinstance(response, list):
            response = "".join(response)
        d[output_field] = response
        return d


async def llm_map(
    input_path: str,
    output_path: str,
    prompt_template: str,
    output_field: str,
    max_concurrent: int = 30,
):
    """
    Reads a JSONL file, applies a prompt template, calls an LLM concurrently,
    and writes the results to a new JSONL file.

    Args:
        input_path: Path to the source .jsonl file.
        output_path: Path to write the results.
        prompt_template: A format string (e.g., "Tell me about {topic}").
        output_field: The new key to add to the JSON object.
    """
    with open(input_path) as f:
        items = [json.loads(line) for line in f]

    logger.info(f"Loaded {len(items)} items for LLM processing.")

    semaphore = asyncio.Semaphore(max_concurrent)

    results = []
    tasks = [
        asyncio.create_task(llm_call(LLM, d, prompt_template, output_field, semaphore))
        for d in items
    ]
    for fut in asyncio.as_completed(tasks):
        results.append(await fut)
        if len(results) % 10 == 0:
            logger.info(
                f"{len(results)} / {len(tasks)} tasks done ({100 * len(results) / len(tasks):.1f}%)."
            )

    with open(output_path, "w") as f:
        f.write("\n".join(json.dumps(d) for d in results) + "\n")


def main(
    input_path: str,
    output_path: str,
    prompt_template_path: str,
    output_field: str,
    max_concurrent: int = 30,
):
    with open(prompt_template_path) as f:
        prompt_template = f.read()

    asyncio.run(
        llm_map(input_path, output_path, prompt_template, output_field, max_concurrent)
    )


if __name__ == "__main__":
    initialize_logger(level="INFO")
    fire.Fire(main)
