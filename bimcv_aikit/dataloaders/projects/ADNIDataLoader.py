from numpy import unique
from pandas import read_csv
from sklearn.utils.class_weight import compute_class_weight
from torch import as_tensor
from torch.nn.functional import one_hot

import monai.data as data
from monai import transforms
from bimcv_aikit.monai.transforms import DeleteBlackSlices

config_default = {}

class ADNIDataLoader:
    def __init__(self, path: str, sep: str = ",", classes: list = ["CN", "AD"], map_labels_dict: dict = None, config: dict = config_default):

        df = read_csv(path, sep=sep)
        if map_labels_dict:
            map_labels = map_labels_dict
            df = df.loc[df["Research Group"].isin(list(map_labels.keys()))]
        elif classes:
            df = df.loc[df["Research Group"].isin(classes)]
            map_labels = {class_: i for i, class_ in enumerate(classes)}
        df["intLabel"] = df["Research Group"].map(map_labels)
        n_classes = len(unique(df["intLabel"].values))
        onehot = lambda x: one_hot(as_tensor(x), num_classes=n_classes).float()
        df["onehot"] = df["intLabel"].apply(onehot)
        self.groupby = df.groupby("Partition")
        self.class_weights = compute_class_weight(
            class_weight="balanced", 
            classes=unique(self.groupby.get_group("train")["intLabel"].values), 
            y=self.groupby.get_group("train")["intLabel"].values
        )
        self.transforms = transforms.Compose(
            [
                transforms.LoadImaged(keys=["image"], ensure_channel_first=True, image_only=False),
                transforms.ToTensord(keys=["image"]),
                transforms.NormalizeIntensityd(keys=["image"]),
                transforms.ScaleIntensityd(keys=["image"]),
                transforms.CropForegroundd(keys=["image"], source_key="image"),
                DeleteBlackSlices(keys=["image"], threshold=0.5),
                transforms.Resized(keys=["image"], spatial_size=eval(config["input_shape"])),
            ]
        )
        self.config_args = config
        self.test_run = config["test_run"] if "test_run" in config else False

    def __call__(self, partition: str):
        data = [
            {"image": img_path, "label": label}
            for img_path, label in zip(self.groupby.get_group(partition)["Path"].values, self.groupby.get_group(partition)["onehot"].values)
        ]
        if self.test_run:
            data = data[:16]
        dataset = data.CacheDataset(data=data, transform=self.transforms, **self.config_args)
        return data.DataLoader(dataset, **self.config_args)