# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import queue
from collections import defaultdict
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from threading import Thread
from time import monotonic as timer, sleep

import dacite
import fire
import yaml
from src import local_mcp as MCP
from src.args import RunArgs
from src.data import Rollout
from src.decomp import rollout as decomp_rollout
from src.env import Env, HEADER
from src.envs import (
    CleverDecompEnv,
    CleverMultiEnv,
    CleverProofEnv,
    CleverSpecEnv,
    LongHeaderDecompEnv,
    LongHeaderMultiEnv,
    LongHeaderProofEnv,
    VerinaDecompEnv,
    VerinaMultiEnv,
    VerinaProofEnv,
)
from src.envs.decomp_env import DecompEnvMixin, MultiEnvMixin
from src.linear import rollout as linear_rollout
from src.multi import rollout as multi_agent_rollout
from src.pool import ResourcePool
from src.queue import ZmqQueue
from src.repl import LeanRepl
from src.utils import (
    get_global_rank,
    get_load,
    get_master_port,
    get_world_size,
    initialize_logger,
    ThreadGroup,
)
from src.vllm import init_vllm

logger = getLogger()


def worker(
    q: ZmqQueue,
    dump_q: queue.Queue,
    done_q: ZmqQueue,
    env: Env,
    pool: ResourcePool,
    args: RunArgs,
) -> None:
    try:
        while True:
            task = q.get()
            if task is None:
                logger.info("Received termination signal.")
                dump_q.put(None)
                done_q.put(None)
                break
            logger.info(
                f"Starting work on task {task['id']} ({task.get('function_name', 'unnamed')})"
            )
            if args.provers_per_goal > 0:
                assert isinstance(env, DecompEnvMixin)
                result = decomp_rollout(env, pool, task, args)
            elif args.n_subagents > 0:
                assert isinstance(env, MultiEnvMixin)
                result = multi_agent_rollout(env, pool, task, args)
            else:
                result = linear_rollout(env, pool, task, args)
            logger.info(f"Env loop terminated: success={result.outcomes['pass']}")
            dump_q.put(result)
    finally:
        q.close_thread()
        done_q.close_thread()


def feed_queue(q: ZmqQueue, args: RunArgs):
    # load tasks
    with open(args.problems) as f:
        tasks = [json.loads(line) for line in f]

    # count trajectories
    trajs_dir = Path(args.dump_dir) / "trajectories"
    jsonls = list(trajs_dir.glob("*.jsonl")) if trajs_dir.exists() else []
    per_id = defaultdict(int)
    for fn in jsonls:
        with fn.open() as f:
            for line in f:
                d = json.loads(line)
                per_id[d["task"]["id"]] += 1

    # feed missing attempts
    n_sent = 0
    for i in range(args.n_attempts):
        for task in tasks:
            if i >= per_id[task["id"]]:
                # Add flags from args to task
                if args.use_mcp:
                    task["use_mcp"] = True
                if args.use_cheatsheet:
                    task["use_cheatsheet"] = True
                # Pass prompt path for ablation studies
                task["prompt_path"] = args.prompt_path
                q.put(task)
                n_sent += 1
    logger.info(f"Sent {n_sent} / {len(tasks) * args.n_attempts} missing tasks")
    for _ in range(get_world_size() * args.n_worker_threads):
        q.put(None)  # termination signal


def finalize(done_q: ZmqQueue, args: RunArgs):
    for _ in range(get_world_size() * args.n_worker_threads):
        item = done_q.get()
        logger.info(f"end thread received {item}")
    # all workers terminated
    logger.info("Finalizing run")


def dump(dump_q: queue.Queue, args: RunArgs):
    rank = get_global_rank()
    done_count = 0
    traj_path = Path(args.dump_dir) / "trajectories" / f"worker_{rank:04d}.jsonl"
    traj_path.parent.mkdir(exist_ok=True, parents=True)
    with traj_path.open("a") as f:
        while True:
            data: Rollout | None = dump_q.get()
            if data is None:
                done_count += 1
                if done_count >= args.n_worker_threads:
                    break
                continue
            f.write(json.dumps(data.to_dict()) + "\n")
            f.flush()


def log_load(args: RunArgs, interval_sec: float = 60):
    rank = get_global_rank()
    log_path = Path(args.dump_dir) / "worker_stats" / f"worker_{rank:04d}.jsonl"
    log_path.parent.mkdir(exist_ok=True, parents=True)
    with log_path.open("a") as f:
        while True:
            start_time = timer()

            stats = get_load()
            timestamp = datetime.now(timezone.utc).isoformat()
            log_entry = {
                "timestamp": timestamp,
                **stats,
            }
            f.write(json.dumps(log_entry) + "\n")
            f.flush()

            work_duration = timer() - start_time
            sleep_duration = interval_sec - work_duration

            if sleep_duration > 0:
                sleep(sleep_duration)


def build_env(task_name: str) -> Env:
    match task_name:
        case "clever_proof":
            return CleverProofEnv()
        case "clever_spec":
            return CleverSpecEnv()
        case "verina_proof":
            return VerinaProofEnv()
        case "longheader_proof":
            return LongHeaderProofEnv()
        case "verina_multi":
            return VerinaMultiEnv()
        case "verina_decomp":
            return VerinaDecompEnv()
        case "clever_multi":
            return CleverMultiEnv()
        case "clever_decomp":
            return CleverDecompEnv()
        case "longheader_multi":
            return LongHeaderMultiEnv()
        case "longheader_decomp":
            return LongHeaderDecompEnv()
        case _:
            raise ValueError("unknown task type")


def main(config_path: str):
    initialize_logger(level="INFO")

    with open(config_path) as f:
        config_dict = yaml.safe_load(f)
    if "config" in config_dict:
        config_dict = config_dict["config"]
    args: RunArgs = dacite.from_dict(data_class=RunArgs, data=config_dict)

    logger.info(f"Started successfully with config: {args}")

    rank = get_global_rank()
    q = ZmqQueue(is_server=rank == 0, port=get_master_port() + 1)
    done_q = ZmqQueue(is_server=rank == 0, port=q.port + 1)
    dump_q = queue.Queue()

    if args.needs_vllm:
        init_vllm(args)

    with ThreadGroup() as g:
        if rank == 0:
            g.go(feed_queue, q=q, args=args)
            g.go(finalize, done_q=done_q, args=args)

        g.go(dump, dump_q=dump_q, args=args)
        Thread(target=log_load, args=(args,), daemon=True).start()  # don't join this

        def new_repl():
            return LeanRepl(header=HEADER, max_mem_mb=40 * 1024)

        pool = ResourcePool(args.max_repls, args.max_usage, env_ctor=new_repl)
        pool.start()

        if args.use_mcp:
            MCP.initialize(
                start_leanexplore=args.use_leanexplore,
                start_loogle=args.use_loogle,
            )

        for i in range(args.n_worker_threads):
            env = build_env(args.task)
            g.go(
                worker,
                name=f"worker-{i}",
                q=q,
                dump_q=dump_q,
                done_q=done_q,
                env=env,
                pool=pool,
                args=args,
            )

    pool.shutdown()
    q.close()
    done_q.close()


if __name__ == "__main__":
    fire.Fire(main)
