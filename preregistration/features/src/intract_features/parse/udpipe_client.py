"""Client of the local UDPipe 2 server: the registered sentences in, one parse per sentence out.

Promoted from presub/translated_union/scripts/tu4u_udpipe.py (TU-4u). Each registered sentence goes on its own
line with tokenizer=presegmented, so UDPipe tokenises, tags and parses but cannot move a sentence boundary (S3: "Both
parsers ... take these sentences"), as in error_model's udpipe_api2.py raw mode. Only a server on 127.0.0.1 may
receive text, and requests bypass any proxy the environment names: nothing leaves the node, and the public LINDAT
service is never used.

TU-4u sent 500 sentences per request across texts. The server batches a request's sentences in arrival order,
--batch_size (32) at a time, without sorting them (udpipe2_server.py at the pinned commit), so in such a request a
text's batches depend on its neighbours. By default the stage sends one text's sentences per request
(parse.call_groups), so a text's parse does not depend on which texts share its shard (DESIGN.md, Determinism),
and whether UDPipe's output is invariant to batch composition, which is untested, does not matter.

Refusals. The server answers HTTP 400 when a presegmented line holds more than 1,000 words (Model._read raises
TooLongError at the pinned commit) and when a request is larger than --max_request_size. Either would otherwise
stop every text of the shard, and a resubmission would fail the same way. On either, the client resends that call's
sentences one per request, and a sentence refused as too long comes back as parse.Refused: the artefact keeps its
block, marked `# refused`, and the run record counts it. A request over the size limit is not sent at all, because
the server answers it before reading the body and the client would see a broken connection instead of the answer.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence

from intract_features.parse import Refused, Token, tokens_from_conllu

LOCAL_PREFIX = "http://127.0.0.1:"
# The texts the server sends (text/plain, HTTP 400) at the pinned commit: respond_error after TooLongError, raised by
# Model._read when a sentence has more than 1,000 words (1,001 with the root node), on the tokenizer path that
# presegmented input takes and on the path that reads CoNLL-U input; and the POST handler's size check.
TOO_LONG_PREFIXES = ("During tokenization, sentence longer than 1000 words was found",
                     "Sentence longer than 1000 words was found on input")
PAYLOAD_TOO_LARGE = "The payload size is too large."
# The reason written as `# refused = ...` in the artefact.
TOO_LONG_REASON = "udpipe2 server: sentence longer than 1000 words"

# An opener with no proxy: the body of every request holds the text, and it must go to this node's server whatever
# http_proxy or the system settings say (the ARC jobs set no proxy, but the guarantee should not rest on that).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class UDPipeRefusal(RuntimeError):
    """The server answered with a client error (HTTP 4xx), which repeating the request cannot change."""

    def __init__(self, code: int | None, body: str, model: str):
        super().__init__(f"UDPipe refused the request for {model!r}: HTTP {code} {body[:500]}")
        self.code, self.body = code, body


class SentenceTooLong(UDPipeRefusal):
    """A presegmented line over the server's limit of 1,000 words."""


class PayloadTooLarge(UDPipeRefusal):
    """A request larger than the server's --max_request_size (code None when the client refused to send it)."""


def refusal_from(code: int, body: str, model: str) -> UDPipeRefusal:
    """The exception for a 4xx answer, told apart by the upstream message it carries."""
    text = body.lstrip()
    if text.startswith(TOO_LONG_PREFIXES):
        return SentenceTooLong(code, body, model)
    if text.startswith(PAYLOAD_TOO_LARGE):
        return PayloadTooLarge(code, body, model)
    return UDPipeRefusal(code, body, model)


def check_local(base_url: str) -> str:
    """Refuse any server that is not on this node's loopback address; return the URL without a trailing slash."""
    if not base_url.startswith(LOCAL_PREFIX):
        raise ValueError(f"only a local UDPipe server may receive text, not {base_url!r}")
    return base_url.rstrip("/")


def wait_for_server(base_url: str, timeout: float, poll: float, *, probe_timeout: float,
                    alive: Callable[[], bool] | None = None, sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> float:
    """Poll GET /models until the server answers; return the seconds waited.

    Each probe waits at most `probe_timeout` seconds. Raises RuntimeError at once if `alive` reports the process
    gone, and TimeoutError after `timeout` seconds. The presub jobs polled 120 times at 5 s; UDPipe's start took
    185 s on L40S (TU-4u log).
    """
    url = check_local(base_url) + "/models"
    t0 = clock()
    while True:
        try:
            with _OPENER.open(url, timeout=probe_timeout) as r:
                if r.status == 200:
                    return clock() - t0
        except (urllib.error.URLError, OSError):
            pass
        if alive is not None and not alive():
            raise RuntimeError("the server process exited before it answered")
        if clock() - t0 > timeout:
            raise TimeoutError(f"no answer from {url} within {timeout:.0f} s")
        sleep(poll)


def split_blocks(conllu: str) -> list[str]:
    """The sentence blocks of a CoNLL-U string: blank-line separated blocks that hold at least one word line.

    TU-4u kept every non-empty block. The upstream server also writes generator, model and licence comments at the
    start of a CoNLL-U result (udpipe2_server.py at the pinned commit); should they ever stand in a block of their
    own, a block of comments alone must not count as a sentence, or every request would fall back.
    """
    return [b for b in conllu.split("\n\n") if any(ln and not ln.startswith("#") for ln in b.split("\n"))]


def block_tokens(block: str) -> list[Token] | None:
    """Tokens of one returned sentence block; UDPipe's own comments (sent_id, newdoc, newpar, text) are dropped."""
    body = [ln for ln in block.split("\n") if ln and not ln.startswith("#")]
    return tokens_from_conllu(body) if body else None


class UDPipeClient:
    """Requests to one model on a local server, with TU-4u's retries, and statistics for the run record.

    Every setting comes from config/stages/parse_udpipe.toml; `sleep` is replaceable for tests.
    """

    def __init__(self, base_url: str, model: str, *, tokenizer: str, timeout: float, retries: int,
                 retry_sleep: float, max_request_bytes: int, sleep: Callable[[float], None] = time.sleep):
        self.base_url = check_local(base_url)
        self.model, self.tokenizer = model, tokenizer
        self.timeout, self.retries, self.retry_sleep, self._sleep = timeout, retries, retry_sleep, sleep
        self.max_request_bytes = max_request_bytes
        self.requests = self.fallback_requests = self.retried = self.largest_request_bytes = 0
        self.too_long_fallbacks = self.payload_fallbacks = 0
        self.refused_too_long = self.refused_max_whitespace_tokens = self.refused_max_characters = 0
        self.models_reported: set[str] = set()

    def process(self, lines: Sequence[str]) -> str:
        """POST one request of presegmented lines and return the CoNLL-U result.

        A connection failure or server error is retried after a pause. A 4xx answer is not, because repeating it
        cannot help; it raises SentenceTooLong, PayloadTooLarge or UDPipeRefusal. A request larger than the server's
        limit raises PayloadTooLarge without being sent.
        """
        data = urllib.parse.urlencode({"model": self.model, "tokenizer": self.tokenizer, "tagger": "", "parser": "",
                                       "data": "\n".join(lines) + "\n"}).encode("utf-8")
        if len(data) > self.max_request_bytes:
            raise PayloadTooLarge(None, f"{PAYLOAD_TOO_LARGE} ({len(data)} bytes, limit {self.max_request_bytes}; "
                                        "not sent)", self.model)
        self.largest_request_bytes = max(self.largest_request_bytes, len(data))
        request = urllib.request.Request(self.base_url + "/process", data=data)
        last: Exception | None = None
        for attempt in range(self.retries):
            if attempt:
                self.retried += 1
                self._sleep(self.retry_sleep)
            try:
                with _OPENER.open(request, timeout=self.timeout) as r:
                    answer = json.loads(r.read().decode("utf-8"))
                self.requests += 1
                if answer.get("model"):
                    self.models_reported.add(str(answer["model"]))
                return answer["result"]
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    raise refusal_from(e.code, e.read().decode("utf-8", errors="replace"), self.model) from e
                last = e
            except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
                last = e
        raise RuntimeError(f"UDPipe server failed for {self.model!r} after {self.retries} attempts: {last}")

    def _refused(self, text: str) -> Refused:
        self.refused_too_long += 1
        self.refused_max_whitespace_tokens = max(self.refused_max_whitespace_tokens, len(text.split()))
        self.refused_max_characters = max(self.refused_max_characters, len(text))
        return Refused(TOO_LONG_REASON)

    def parse(self, texts: list[str]) -> list[list[Token] | Refused | None]:
        """Parse one call's sentences in one request; on a count mismatch or a refusal, one request per sentence.

        As in TU-4u: a line that yields no sentence keeps None, and a line that yields two is an error. A sentence
        the server refuses as too long becomes Refused.
        """
        try:
            blocks = split_blocks(self.process(texts))
        except SentenceTooLong:
            if len(texts) == 1:
                return [self._refused(texts[0])]
            self.too_long_fallbacks += 1
        except PayloadTooLarge:
            if len(texts) == 1:
                raise
            self.payload_fallbacks += 1
        else:
            if len(blocks) == len(texts):
                return [block_tokens(b) for b in blocks]
            self.fallback_requests += 1
        out: list[list[Token] | Refused | None] = []
        for text in texts:
            try:
                one = split_blocks(self.process([text]))
            except SentenceTooLong:
                out.append(self._refused(text))
                continue
            if len(one) > 1:
                raise RuntimeError(f"UDPipe split one registered sentence into {len(one)}: {text[:80]!r}")
            out.append(block_tokens(one[0]) if one else None)
        return out

    def stats(self) -> dict:
        """Request statistics for the run record."""
        return {"requests": self.requests, "fallback_requests": self.fallback_requests, "retried": self.retried,
                "too_long_fallbacks": self.too_long_fallbacks, "payload_fallbacks": self.payload_fallbacks,
                "refused_too_long": self.refused_too_long,
                "refused_max_whitespace_tokens": self.refused_max_whitespace_tokens,
                "refused_max_characters": self.refused_max_characters,
                "largest_request_bytes": self.largest_request_bytes, "max_request_bytes": self.max_request_bytes,
                "models_reported": sorted(self.models_reported)}

    def model_problem(self) -> str | None:
        """A message if the server reported serving another model than the one requested, else None.

        The server answers with the first name of the model it served and looks a requested name up exactly
        (udpipe2_server.py at the pinned commit), so a request by the full name reports that name.
        """
        other = self.models_reported - {self.model}
        return f"the UDPipe server reported model(s) {sorted(other)} for {self.model!r}" if other else None
