import logging
import glob
import re
import os

from tqdm.auto import tqdm
from typing import List

from semsearch.pipeline.doc import Doc
from semsearch.feeders import FileFeeder  # noqa


logger = logging.getLogger(__name__)


def install(package:str):
    # Not really recommended, see:
    # https://pip.pypa.io/en/latest/user_guide/#using-pip-from-your-program
    # Perhaps this should be:
    # subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'my_package'])
    try:
        from pip import main as pipmain
    except ImportError:
        from pip._internal import main as pipmain

    pipmain(['install', package])


try:
    import webvtt
except ImportError:
    logger.warning("Installing webvtt!")
    install('webvtt-py')
    import webvtt


class VTTFeeder(FileFeeder):
    def __init__(self, data_path: str, globmask:str, batch_size: int = 1, *args, **kwargs) -> None:
        super().__init__(data_path, batch_size, *args, **kwargs)

        logger.info(f"VTT feeder data path: {data_path}")

        self.files = self._gather_transcripts(data_path, globmask)
        self.episode_data = self._gather_episode_data(data_path)
        logger.info(f"Found a total of {len(self.files)} files")


    def _gather_transcripts(self, data_dir:str, mask:str):
        return sorted(
            glob.glob(os.path.join(data_dir, mask))
        )


    def _gather_episode_data(self, data_dir:str):
        ep_data = {}
        with open(os.path.join(data_dir, "episode_names.txt")) as f:
            for line in f.readlines():
                line = line.strip()
                ep_num = re.findall("(?<=#)\d+", line)[0]
                line = re.sub(f"^{ep_num} ", "", line)
                guest_and_title = line.split(" | ")[0]
                ep_data[ep_num] = {
                    "guest": guest_and_title.split(": ")[0],
                    "title": ": ".join(guest_and_title.split(": ")[1:])
                }

        return ep_data


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
            text = " ".join([caption.text for caption in webvtt.read(sfile)])

            # We index a Document with only 1 section per sentence
            doc = Doc(external_id=str(s_i), text="")
            doc.name = f"{ep_info['title']}_#{s_i}"
            doc.add_section(section_number=s_i, name="", text=text, weight=1)

            transformed_data.append(doc)
            current_batch += 1

            # Send the current batch if is of the size of batch_size
            if current_batch == self.batch_size:
                yield transformed_data
                transformed_data = []
                current_batch = 0

        if transformed_data:
            yield transformed_data

