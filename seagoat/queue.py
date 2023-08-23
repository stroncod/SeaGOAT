# pylint: disable=import-outside-toplevel
import logging
from collections import namedtuple
from multiprocessing import Manager
from multiprocessing import Process
from multiprocessing import Queue
from typing import Optional


Task = namedtuple("Task", ["name", "args", "kwargs"])


class TaskQueue:
    def __init__(
        self,
        repo_path: str,
        minimum_chunks_to_analyze: Optional[int] = None,
    ):
        self._task_queue = Queue()
        self._worker_process = Process(target=self._worker_function, args=(repo_path,))
        self.minimum_chunks_to_analyze = minimum_chunks_to_analyze
        self._worker_process.start()

    def _worker_function(self, repo_path: str):
        logging.info("Starting worker process...")
        chunks_to_analyze = Queue()

        from seagoat.engine import Engine

        seagoat_engine = Engine(repo_path)

        remaining_chunks_to_analyze = seagoat_engine.analyze_codebase(
            self.minimum_chunks_to_analyze
        )

        logging.info("Analyzed the minimum number of chunks needed to operate. ")
        if remaining_chunks_to_analyze:
            logging.info(
                "Note, %s chunks need to be analyzed for optimum performance.",
                len(remaining_chunks_to_analyze),
            )
        else:
            logging.info(
                "Analyzed all chunks!",
            )

        for chunk in remaining_chunks_to_analyze:
            chunks_to_analyze.put(chunk)

        context = {
            "seagoat_engine": seagoat_engine,
            "chunks_to_analyze": chunks_to_analyze,
        }

        while True:
            while self._task_queue.qsize() == 0 and chunks_to_analyze.qsize() > 0:
                logging.info(
                    "Note, %s chunks left to analyze.", chunks_to_analyze.qsize()
                )
                chunk = chunks_to_analyze.get()
                logging.info("Processing chunk %s...", chunk)
                seagoat_engine.process_chunk(chunk)
                if chunks_to_analyze.empty():
                    logging.info(
                        "Analyzed all chunks!",
                    )

            task = self._task_queue.get()

            if task.name == "shutdown":
                break

            handler_name = f"handle_{task.name}"
            handler = getattr(self, handler_name, None)
            if handler:
                kwargs = dict(task.kwargs or {})
                if "__result_queue" in kwargs:
                    del kwargs["__result_queue"]
                result = handler(context, *task.args, **kwargs)
                task.kwargs.get("__result_queue").put(result)

    def handle_query(self, context, **kwargs):
        context["seagoat_engine"].query(kwargs["query"])
        context["seagoat_engine"].fetch_sync(
            limit_clue=kwargs["limit_clue"],
            context_above=int(kwargs["context_above"]),
            context_below=int(kwargs["context_below"]),
        )
        return context["seagoat_engine"].get_results()

    def handle_get_stats(self, context):
        engine = context["seagoat_engine"]
        chunks_to_analyze = context["chunks_to_analyze"]

        return {
            "queue": {
                "size": chunks_to_analyze.qsize() + self._task_queue.qsize(),
            },
            "chunks": {
                "analyzed": len(engine.cache.data["chunks_already_analyzed"]),
                "unanalyzed": chunks_to_analyze.qsize(),
            },
        }

    def enqueue(self, task_name, *args, wait_for_result=True, **kwargs):
        result_queue = Manager().Queue()
        task = Task(
            name=task_name, args=args, kwargs={**kwargs, "__result_queue": result_queue}
        )
        self._task_queue.put(task)
        if wait_for_result:
            return result_queue.get()

        return None

    def shutdown(self):
        self._task_queue.put(Task(name="shutdown", args=None, kwargs=None))
        self._worker_process.join()
