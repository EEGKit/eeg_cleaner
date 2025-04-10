# NICE-EEG Cleaner
# Copyright (C) 2019 - Authors of NICE-EEG-Cleaner
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# You can be released from the requirements of the license by purchasing a
# commercial license. Buying such a license is mandatory as soon as you
# develop commercial activities as mentioned in the GNU Affero General Public
# License version 3 without disclosing the source code of your own
# applications.
#
import json
from pathlib import Path

import mne
import numpy as np
from mne.utils import logger


def _get_git_hash():
    import subprocess

    t_path = Path(__file__).parent.resolve()
    label = subprocess.check_output(
        ["git", "-C", t_path, "describe", "--always"]
    ).strip()
    return label.decode()


def _get_json_fname(path):
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_file():
        path = path.parent
    json_fname = path / "eeg_cleaner.json"
    return json_fname


def read_log(path):
    """
    Read the json file if exists, otherwise, create an "empty" file.
    """
    json_fname = _get_json_fname(path)
    if json_fname.exists():
        with open(json_fname, "r") as f:
            logs = json.load(f)
    else:
        logs = {}

    if "raws" not in logs:
        logs["raws"] = {}
    if "epochs" not in logs:
        logs["epochs"] = {}
    if "icas" not in logs:
        logs["icas"] = {}
    git_hash = _get_git_hash()
    if "config" not in logs:
        logs["config"] = {"version": git_hash}
    else:
        prev_hash = logs["config"]["version"]
        if prev_hash != git_hash:
            logger.warning(
                "The specified subject was cleaned with a previous "
                f"version of EEG cleaner. ({prev_hash}). The new version "
                f"({git_hash}) might fail."
            )

    save_log(path, logs)

    return logs


def save_log(path, logs):
    """
    Save the json file, ensuring all the needed keys are there
    """
    json_fname = _get_json_fname(path)

    if "raws" not in logs:
        logs["raws"] = {}
    if "epochs" not in logs:
        logs["epochs"] = {}
    if "icas" not in logs:
        logs["icas"] = {}
    git_hash = _get_git_hash()
    if "config" not in logs:
        logs["config"] = {"version": git_hash}
    else:
        prev_hash = logs["config"]["version"]
        if prev_hash != git_hash:
            logger.warning(
                "The specified subject was cleaned with a previous "
                f"version of EEG cleaner. ({prev_hash}). The new version "
                f"({git_hash}) might fail."
            )
    with open(json_fname, "w") as f:
        json.dump(logs, f)


def update_log(path, inst):
    """
    Update the log and save the json file
    """
    logger.info(f"Updating log for {path}")
    logs = read_log(path)
    if isinstance(inst, mne.io.BaseRaw):
        fname = inst.filenames[0].name
        t_log = logs["raws"].get(fname, {})
        t_log["bads"] = inst.info["bads"]
        logger.info(f"Updating bad channels {t_log['bads']}")
        if fname not in logs["raws"]:
            logs["raws"][fname] = t_log
    elif isinstance(inst, mne.BaseEpochs):
        fname = inst.filename.name
        t_log = logs["epochs"].get(fname, {})
        _check_epochs_params(inst, t_log)
        t_log["bads"] = inst.info["bads"]
        logger.info(f"Updating bad channels {t_log['bads']}")

        t_log["selection"] = inst.selection.tolist()
        dropped = [
            i
            for i, x in enumerate(inst.drop_log)
            if "Inspection" in x or "USER" in x
        ]
        logger.info(f"Updating bad epochs {dropped}")

        if fname not in logs["epochs"]:
            logs["epochs"][fname] = t_log
    elif isinstance(inst, mne.preprocessing.ICA):
        fname = path.name
        t_log = logs["icas"].get(fname, {})
        _check_ica_params(inst, t_log)
        t_log["exclude"] = inst.exclude
        if fname not in logs["icas"]:
            logs["icas"][fname] = t_log
    save_log(path, logs)


def _check_epochs_params(epochs, t_log):
    if "params" not in t_log:
        t_log["params"] = {
            "tmin": epochs.tmin,
            "tmax": epochs.tmax,
            "events": epochs.events[:, 0].tolist(),
        }
    else:
        if epochs.tmin != t_log["params"]["tmin"]:
            raise ValueError(
                "Epochs were cut differently: "
                f"tmin was {t_log['params']['tmin']} and now is {epochs.tmin}"
            )
        if epochs.tmax != t_log["params"]["tmax"]:
            raise ValueError(
                "Epochs were cut differently: "
                f"tmax was { t_log['params']['tmax']} and now is {epochs.tmax}"
            )

        # Check events (saved events is subset of epochs.events)
        this_selection = epochs.selection
        prev_selection = t_log.get("selection", np.arange(len(epochs)))
        inter = np.intersect1d(this_selection, prev_selection)
        this_events = epochs.events[:, 0].tolist()
        to_check = [
            this_events[i] for i, x in enumerate(this_selection) if x in inter
        ]
        prev_events = t_log["params"]["events"]
        if not all(x in prev_events for x in to_check):
            raise ValueError("Epochs event samples do not match")


def _check_ica_params(ica, t_log):
    if "params" not in t_log:
        t_log["params"] = {
            "ch_names": ica.ch_names,
            "fit_params": ica.fit_params,
            "n_components": ica.n_components,
            "highpass": ica.info["highpass"],
            "lowpass": ica.info["lowpass"],
            "sfreq": ica.info["sfreq"],
        }
    else:
        if ica.ch_names != t_log["params"]["ch_names"]:
            raise ValueError("ICA channels names do not match.")
        if ica.fit_params != t_log["params"]["fit_params"]:
            raise ValueError("ICA fit params do not match.")

        if ica.n_components != t_log["params"]["n_components"]:
            raise ValueError("ICA number of components do not match.")
        if ica.info["highpass"] != t_log["params"]["highpass"]:
            raise ValueError("ICA highpass filter do not match.")
        if ica.info["lowpass"] != t_log["params"]["lowpass"]:
            raise ValueError("ICA lowpass filter do not match.")
        if ica.info["sfreq"] != t_log["params"]["sfreq"]:
            raise ValueError("ICA sample frequency do not match.")
