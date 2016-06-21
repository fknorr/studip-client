import threading, ctypes

from multiprocessing import cpu_count
from threading import Thread, Condition, Lock
from copy import deepcopy


class ExitThread(BaseException):
    pass

class ThreadPool:
    def __init__(self, n_threads=cpu_count(), local_state={}):
        self.threads = [ Thread(target=lambda i=i: self.thread_main(i, deepcopy(local_state)))
                for i in range(n_threads) ]

        self.queue = []
        self.results = []
        self.last_req_no = -1
        self.last_finished_no = -1
        self.done_at_no = -1
        self.lock = Lock()
        self.thread_cv = Condition(self.lock)
        self.iter_cv = Condition(self.lock)
        self.exception = None

        for thread in self.threads:
            thread.start()

    def init_thread(self, local_state):
        pass

    def cleanup_thread(self, local_state):
        pass

    def execute_task(self, local_state, task):
        pass

    def thread_main(self, i, local_state):
        local_state["thread_no"] = i
        self.init_thread(local_state)
        try:
            while True:
                with self.lock:
                    self.thread_cv.wait_for(lambda: self.queue)
                    task = self.queue.pop(0)
                result = self.execute_task(local_state, task)
                with self.lock:
                    self.results.append(result)
                    self.last_finished_no += 1
                    self.iter_cv.notify()
        except ExitThread:
            pass
        except BaseException as e:
            with self.lock:
                self.exception = e
        finally:
            self.cleanup_thread(local_state)

    def defer(self, task):
        with self.lock:
            self.done_at_no = -1
            self.last_req_no += 1
            self.queue.append(task)
            self.thread_cv.notify()

    def __iter__(self):
        with self.lock:
            while self.last_finished_no <= self.done_at_no:
                self.iter_cv.wait_for(lambda: self.last_finished_no >= self.done_at_no
                        or self.results or self.exception)
                if self.exception:
                    e = self.exception
                    self.exception = None
                    raise e
                elif self.results:
                    yield self.results.pop(0)
                else:
                    break
        raise StopIteration()

    def done(self):
        with self.lock:
            self.done_at_no = self.last_req_no

    def destroy(self):
        for thread in self.threads:
            # raise ExitThread in every thread
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident),
                ctypes.py_object(ExitThread))
        with self.lock:
            # Wake up all waiting threads to handle exception
            self.thread_cv.notify_all()
        for thread in self.threads:
            thread.join()
        if self.exception:
            e = self.exception
            self.exception = None
            raise e

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
