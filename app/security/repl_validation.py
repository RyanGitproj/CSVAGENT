"""Static checks for code passed to the dataframe Python REPL tool."""

from __future__ import annotations

import re

_DANGEROUS_RE = re.compile(
    r"|".join(
        [
            r"\bimport\b",
            r"\bfrom\b",
            r"\bos\.",
            r"\bsys\.",
            r"\bsubprocess\.",
            r"\bshutil\.",
            r"\bexec\b",
            r"\beval\b",
            r"\bopen\b",
            r"\bcompile\b",
            r"\binput\b",
            r"\bbuiltins\b",
            r"\bthreading\b",
            r"\bconcurrent\b",
            r"\basyncio\b",
            r"\bgetattr\b",
            r"\bsetattr\b",
            r"\bdelattr\b",
            r"\brun\b",
            r"\bPopen\b",
            r"\bos\.popen\b",
            r"\bwhile\b",
            r"\btry\b",
            r"\bexcept\b",
            r"\bfinally\b",
            r"\bwith\b",
            r"\brmdir\b",
            r"\bunlink\b",
            r"\bmkdir\b",
            r"\bkill\b",
            r"\bchmod\b",
            r"\bchown\b",
            r"\bchgrp\b",
            r"\brmtree\b",
            r"\bfork\b",
            r"\bspawn\b",
            r"\bsignal\b",
            r"\bsocket\b",
            r"\burllib\b",
            r"\bhttp\.client\b",
            r"\bftplib\b",
            r"\btelnetlib\b",
            r"\bsmtplib\b",
            r"\btempfile\b",
            r"\bpickle\b",
            r"\bmarshal\b",
            r"\bdill\b",
            r"\bctypes\b",
            r"\bmultiprocessing\b",
        ]
    )
)

_DF_ASSIGN_RE = re.compile(r"\bdf\.\w+\s*=")

_BLOCKLIST_SUBSTR = (
    "importlib",
    "sys.modules",
    "sys.path",
    "os.environ",
    "os.system",
    "os.fork",
    "inspect.",
    "pickle.",
    "numpy.load",
    "numpy.save",
)


def validate_python_repl_query(code: str) -> None:
    if _DANGEROUS_RE.search(code):
        raise ValueError("This snippet uses constructs that are not allowed in the sandbox.")
    if _DF_ASSIGN_RE.search(code):
        raise ValueError("Modifying the dataframe in place is not allowed.")
    lower = code.lower()
    if any(s in lower for s in _BLOCKLIST_SUBSTR):
        raise ValueError("This snippet contains disallowed keywords for the sandbox.")
