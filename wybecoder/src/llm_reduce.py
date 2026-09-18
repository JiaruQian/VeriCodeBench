# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import asyncio
from pathlib import Path

from logging import getLogger
import fire
from src.utils import initialize_logger, read_jsonl_or_jsonl_dir
from src.llm_map import llm_call


from langchain_google_genai import ChatGoogleGenerativeAI


logger = getLogger()


LLM = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)

SUMMARY = "__SUMMARY__"


async def llm_reduce(
    data: list[dict],
    output_path: str,
    single_document_template: str,
    first_prompt_template: str,
    subsequent_prompt_template: str,
    batch_size: int,
    max_concurrent: int = 30,
):
    """
    Performs hierarchical summarization on a list of text snippets.
    """
    documents = [single_document_template.format(**d) for d in data]

    level = 0
    while len(documents) > 1:
        level += 1
        logger.info(f"--- Processing Level {level} ---")
        logger.info(f"Input texts: {len(documents)}")

        num_batches = max(1, len(documents) // batch_size)
        per_batch = len(documents) // num_batches
        extra = len(documents) % num_batches
        batch_sizes = [per_batch + 1] * extra + [per_batch] * (num_batches - extra)
        logger.info(f"Batch sizes: {batch_sizes}")

        prompt_template = (
            first_prompt_template if level == 1 else subsequent_prompt_template
        )
        semaphore = asyncio.Semaphore(max_concurrent)

        # schedule summarization
        tasks = []
        start_index = 0
        for i, size in enumerate(batch_sizes):
            end_index = start_index + size
            batch = documents[start_index:end_index]
            start_index = end_index

            logger.info(
                f"  Summarizing batch {i + 1}/{num_batches} (size: {len(batch)})..."
            )

            d = {"texts": "\n\n---\n\n".join(batch)}
            task = asyncio.create_task(
                llm_call(LLM, d, prompt_template, SUMMARY, semaphore)
            )
            tasks.append(task)

        # retrieve summaries
        summaries = []
        for fut in asyncio.as_completed(tasks):
            result = await fut
            summaries.append(result[SUMMARY])
            if len(summaries) % 10 == 0:
                logger.info(
                    f"{len(summaries)} / {len(tasks)} tasks done ({100 * len(summaries) / len(tasks):.1f}%)."
                )

        documents = summaries
        logger.info(f"Level {level} complete. Generated {len(documents)} summaries.")

    assert len(documents) == 1
    final = documents[0]
    print(f"FINAL SUMMARY:\n{final}")
    with open(output_path, "w") as f:
        f.write(final)


def main(
    input_path: str,
    output_path: str,
    single_document_template_path: str,
    first_prompt_template_path: str,
    subsequent_prompt_template_path: str,
    batch_size: int,
    max_concurrent: int = 30,
):
    data = read_jsonl_or_jsonl_dir(input_path)

    with open(single_document_template_path) as f:
        single_document_template = f.read()

    with open(first_prompt_template_path) as f:
        first_prompt_template = f.read()

    with open(subsequent_prompt_template_path) as f:
        subsequent_prompt_template = f.read()

    asyncio.run(
        llm_reduce(
            data,
            output_path,
            single_document_template,
            first_prompt_template,
            subsequent_prompt_template,
            batch_size,
            max_concurrent,
        )
    )


if __name__ == "__main__":
    # python -m src.llm_reduce runs/escalate_incorrect.jsonl runs/report.md data/snippet.prompt data/extract.prompt data/join.prompt 8 100
    initialize_logger(level="INFO")
    fire.Fire(main)
