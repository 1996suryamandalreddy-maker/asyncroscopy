import types

import h5py
import numpy as np

from asyncroscopy.software.DataWriter import save_acquisition_hdf5


def test_save_acquisition_hdf5_writes_data_and_xml_leaf_attrs(tmp_path):
    source = types.SimpleNamespace(
        data=np.array([[1, 2], [3, 4]], dtype=np.uint16),
        metadata=types.SimpleNamespace(
            metadata_as_xml="<root><detector>HAADF</detector><empty /></root>",
        ),
    )
    path = tmp_path / "acquisition.h5"

    save_acquisition_hdf5(
        path,
        [
            {
                "name": "images/HAADF",
                "source": source,
                "attrs": {"acquisition_type": "stem_image"},
            }
        ],
    )

    with h5py.File(path, "r") as h5:
        assert h5["images/HAADF"][()].tolist() == [[1, 2], [3, 4]]
        assert h5["images/HAADF"].attrs["acquisition_type"] == "stem_image"
        assert h5["images/HAADF"].attrs["detector"] == "HAADF"
