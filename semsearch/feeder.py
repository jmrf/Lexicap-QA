import copy
import logging
import glob
import re
import os

import datetime as dt

from typing import Dict
from typing import List
from typing import Union

from semsearch.pipeline.doc import Doc    # noqa
from semsearch.feeders import FileFeeder  # noqa


logger = logging.getLogger(__name__)


def install(packages: List[str]) -> None:
    # For more info, see:
    # https://pip.pypa.io/en/latest/user_guide/#using-pip-from-your-program
    import sys
    import subprocess

    for package in packages:
        logger.warning(f"Installing: '{package}'")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])


# Nasty trick to avoid creating a docker image where we install this packages,
# instead we use the base 'semantic-search' docker image and install @ run time
try:
    import webvtt
    import nltk
except ImportError:
    install(["webvtt-py", "nltk"])
    import webvtt
    import nltk

    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")


class VTTFeeder(FileFeeder):
    def __init__(
        self,
        data_path: str,
        globmask: str,
        split_by_time: bool = True,
        time_grouping: int = 60,
        batch_size: int = 1,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(data_path, batch_size, *args, **kwargs)

        logger.info(f"VTT feeder data path: {data_path}")
        self.split_by_time = split_by_time
        self.time_grouping = time_grouping

        # Read data from dir
        self.files = self._gather_transcripts(data_path, globmask)
        self.episode_data = self._gather_episode_data(data_path)
        logger.info(f"Found a total of {len(self.files)} files")

    @staticmethod
    def _gather_transcripts(data_dir: str, mask: str):
        return sorted(glob.glob(os.path.join(data_dir, mask)))

    @staticmethod
    def _gather_episode_data(data_dir: str):
        ep_data = {}
        with open(os.path.join(data_dir, "episode_names.txt")) as f:
            for line in f.readlines():
                line = line.strip()
                ep_num = re.findall("(?<=#)\d+", line)[0]
                line = re.sub(f"^{ep_num} ", "", line)
                guest_and_title = line.split(" | ")[0]
                ep_data[ep_num] = {
                    "guest": guest_and_title.split(": ")[0],
                    "title": ": ".join(guest_and_title.split(": ")[1:]),
                }

        return ep_data

    @staticmethod
    def _sent_split(text: str) -> Dict[str, Union[str, int]]:
        """Divides each document section into several chunks based on
        a NLTK **sentence** tokenizer.
        """
        text_chunks = nltk.tokenize.sent_tokenize(text)
        text_indices = list(
            map(
                lambda m: (m.start(), m.end()) if m else (None, None),
                [re.search(re.escape(text_chunk), text) for text_chunk in text_chunks],
            )
        )

        return [
            {"text": text, "start": indices[0], "end": indices[1]}
            for text, indices in zip(text_chunks, text_indices)
        ]

    @staticmethod
    def _split_with_timestamp(sfile: str):
        chunks = []
        buffer = []
        start = None
        for caption in webvtt.read(sfile):
            text = caption.text
            if not re.search("\w[\.\?\!]$", text):
                buffer.append(text)
                if start is None:
                    start = caption.start
            else:
                chunks.append(
                    {
                        "start": start or caption.start,
                        "end": caption.end,
                        "text": (" ".join(buffer) + text).strip(),
                    }
                )
                buffer = []
                start = None

        return chunks

    @staticmethod
    def _split_with_text_indices(sfile: str):
        text = " ".join([caption.text for caption in webvtt.read(sfile)])
        return VTTFeeder._sent_split(text)

    @staticmethod
    def cluster_in_time(chunks, group_secs: int = 60):
        def parse_ts(ts: str):
            return dt.datetime.strptime(ts, "%H:%M:%S.%f")

        def delta_secs(t1: str, t2: str):
            return (parse_ts(t2) - parse_ts(t1)).seconds

        def add_group():
            groups.append(
                {
                    "start": start["start"],
                    "end": end["end"],
                    "text": " ".join([b["text"] for b in buffer]),
                }
            )

        groups = []
        ini = 0
        fin = 1
        start = chunks[ini]
        end = chunks[fin]
        buffer = [start]
        while fin < len(chunks):
            end = chunks[fin]

            if delta_secs(t1=start["start"], t2=end["end"]) < group_secs:
                buffer.append(end)

            else:
                add_group()
                ini = fin
                start = chunks[ini]
                buffer = [end]

            fin += 1

        if len(buffer) > 0:
            add_group()

        return groups

    def fit(self, x, y=None):
        # Nothing to do here
        return self

    def transform(self, x: List[Doc] = None, errors: List = None) -> List[Doc]:
        logger.info(f"VTTFeeder.transform => Reading from {self.data_path}")

        current_batch = 0
        transformed_data = []
        for s_i, sfile in enumerate(self.files):
            fname = os.path.basename(sfile)

            # Episode number
            ep_num = str(int(re.findall("\d{1,3}", fname)[0]))  # trim leading 0's
            ep_info = self.episode_data[ep_num]

            # Read transcript and split in sentences
            if self.split_by_time:
                chunks = self._split_with_timestamp(sfile)
                chunks = self.cluster_in_time(chunks)
            else:
                chunks = self._split_with_text_indices(sfile)

            # We index a Document with only as many sections as 1 minute audio chunks
            extra_fields = {
                "type": "content", # NOTE: required for the gateway-api
                "semantic": True,  # NOTE: required for semsearch-inference
                **ep_info,
            }
            doc = Doc(external_id=str(s_i), text="", extra_fields=extra_fields)
            doc.name = f"{ep_info['title']} #{s_i}"
            for c_i, chunk in enumerate(chunks):
                doc.add_section(
                    # Can we add boundary information to a section?
                    # i.e.: (start, end)
                    section_number=c_i, name="", text=chunk["text"], weight=1
                )

            transformed_data.append(doc)
            current_batch += 1

            # Send the current batch if is of the size of batch_size
            if current_batch == self.batch_size:
                yield transformed_data
                transformed_data = []
                current_batch = 0

        if transformed_data:
            yield transformed_data
