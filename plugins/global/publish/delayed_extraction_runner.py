
import sys
import re
import traceback
import pyblish.api


class DelayedExtractionRunner(pyblish.api.InstancePlugin):
    """Consume and execute delayed extractors
    """

    order = pyblish.api.ExtractorOrder + 0.49
    label = "Run Delayed Extractions"

    targets = ["localhost"]

    def process(self, instance):

        if instance.data.get("to_deadline", False):
            return

        context = instance.context
        # Skip if any error occurred
        if not all(result["success"] for result in context.data["results"]):
            self.log.warning("Atomicity not held, aborting.")
            return

        extractors = [(key.split(".")[1], value)
                      for key, value in instance.data.items()
                      if re.match(r"repr\.[a-zA-Z_]*\._delayRun", key)]
        extractors.sort(key=lambda t: t[1].get("order", -1))

        for repr_name, extractor in extractors:

            func = extractor["func"]
            args = extractor.get("args", list())
            kwargs = extractor.get("kwargs", dict())

            self.log.info("Running extractor [%s] for [%s] to [%s]..."
                          % (func.__name__, instance, repr_name))

            try:
                func(*args, **kwargs)
            except Exception as e:
                err_msg = "{file}, line {line}, in {func}: {err}"

                _, _, tb = sys.exc_info()
                last_callstack = traceback.extract_tb(tb)[-1]
                lineno = last_callstack[1]

                errMsg = err_msg.format(file=func.im_class.__module__,
                                        line=lineno,
                                        func=func.__name__,
                                        err=str(e))
                self.log.critical(errMsg)
                raise Exception("Extraction failed, see log for deatil.")
            else:
                extractor["done"] = True
