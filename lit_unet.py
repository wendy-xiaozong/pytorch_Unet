from typing import Union, List
import pytorch_lightning as pl
from torchio import DATA
from torch.utils.data import DataLoader
from data.get_subjects import get_subjects
from data.const import CC359_DATASET_DIR, NFBS_DATASET_DIR, ADNI_DATASET_DIR_1, COMPUTECANADA
from data.transform import get_train_transforms, get_val_transform, get_test_transform
from argparse import ArgumentParser
from data.const import SIZE
from model.unet.unet import UNet
from utils.loss import get_score, dice_loss
import torch.nn.functional as F
from postprocess.visualize import log_all_info
from torch import Tensor
import torchio
import torch


class Lightning_Unet(pl.LightningModule):
    def __init__(self, hparams):
        super(Lightning_Unet, self).__init__()
        self.hparams = hparams
        self.unet = UNet(
            in_channels=1,
            out_classes=1,
            num_encoding_blocks=3,
            out_channels_first_layer=8,
            normalization=hparams.normalization,
            upsampling_type='conv',
            padding=2,
            dropout=0,
        )
        if COMPUTECANADA:
            datasets = [CC359_DATASET_DIR, NFBS_DATASET_DIR, ADNI_DATASET_DIR_1]
        else:
            datasets = [CC359_DATASET_DIR]
        self.subjects = get_subjects()
        num_subjects = len(self.subjects)
        num_training_subjects = int(num_subjects * 0.9)  # （5074+359+21） * 0.9 used for training
        self.training_subjects = self.subjects[:num_training_subjects]
        self.validation_subjects = self.subjects[num_training_subjects:]
        # self.training_subjects = subjects[:10]
        # self.validation_subjects = subjects[10:15]

    def forward(self, x: Tensor) -> Tensor:
        return self.unet(x)

    def train_dataloader(self) -> DataLoader:
        training_transform = get_train_transforms()
        train_imageDataset = torchio.ImagesDataset(self.training_subjects, transform=training_transform)
        training_loader = DataLoader(train_imageDataset,
                                     batch_size=self.hparams.batch_size,
                                     # num_workers=multiprocessing.cpu_count()) would cause RuntimeError('DataLoader
                                     # worker (pid(s) {}) exited unexpectedly' if don't do that
                                     num_workers=8)
        print('Training set:', len(train_imageDataset), 'subjects')
        return training_loader

    def val_dataloader(self) -> DataLoader:
        val_transform = get_val_transform()
        val_imageDataset = torchio.ImagesDataset(self.validation_subjects, transform=val_transform)
        val_loader = DataLoader(val_imageDataset,
                                batch_size=self.hparams.batch_size * 2,
                                # num_workers=multiprocessing.cpu_count())
                                num_workers=8)
        print('Validation set:', len(val_imageDataset), 'subjects')
        return val_loader

    def test_dataloader(self):
        test_transform = get_test_transform()
        # using all the data to test
        test_imageDataset = torchio.ImagesDataset(self.subjects, transform=test_transform)
        test_loader = DataLoader(test_imageDataset,
                                 batch_size=1,  # always one because using different label size
                                 num_workers=8)
        print('Testing set:', len(test_imageDataset), 'subjects')
        return test_loader

    # need to adding more things
    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.parameters(), lr=1e-3)  # ??
        return optimizer

    def _prepare_data(self, batch):
        inputs, targets = batch["img"][DATA], batch["label"][DATA]
        if torch.isnan(inputs).any():
            print("there is nan in input data!")
            inputs[inputs != inputs] = 0
        if torch.isnan(targets).any():
            print("there is nan in targets data!")
            targets[targets != targets] = 0
        # making the label as binary, it is very strange because if the label is not binary
        # the whole model cannot learn at all
        target_bin = torch.zeros(size=targets.size()).type_as(inputs)
        target_bin[targets > 0.5] = 1
        return inputs, target_bin

    def training_step(self, batch, batch_idx):
        inputs, targets = self._prepare_data(batch)
        # print(f"training input range: {torch.min(inputs)} - {torch.max(inputs)}")
        logits = self(inputs)
        probs = torch.sigmoid(logits)
        dice, iou, _, _ = get_score(probs, targets)
        if batch_idx != 0 and batch_idx == 25:  # every epoch only save one fig
            input = inputs.chunk(inputs.size()[0], 0)[0]  # split into 1 in the dimension 0
            target = targets.chunk(targets.size()[0], 0)[0]  # split into 1 in the dimension 0
            logit = probs.chunk(logits.size()[0], 0)[0]  # split into 1 in the dimension 0
            log_all_info(self, input, target, logit, batch_idx, "training")
        # loss = F.binary_cross_entropy_with_logits(logits, targets)
        loss = dice_loss(probs, targets)
        tensorboard_logs = {"train_loss": loss, "train_IoU": iou, "train_dice": dice}
        return {'loss': loss, "log": tensorboard_logs}

    def validation_step(self, batch, batch_id):
        inputs, targets = self._prepare_data(batch)
        # print(f"input shape: {inputs.shape}, targets shape: {targets.shape}")
        # print(f"validation input range: {torch.min(inputs)} - {torch.max(inputs)}")
        logits = self(inputs)
        probs = torch.sigmoid(logits)  # compare the position
        loss = dice_loss(probs, targets)
        dice, iou, sensitivity, specificity = get_score(probs, targets)
        return {'val_step_loss': loss,
                'val_step_dice': dice,
                'val_step_IoU': iou,
                "val_step_sensitivity": sensitivity,
                "val_step_specificity": specificity
                }

    # Called at the end of the validation epoch with the outputs of all validation steps.
    def validation_epoch_end(self, outputs):
        # torch.stack: Concatenates sequence of tensors along a new dimension.
        avg_loss = torch.stack([x['val_step_loss'] for x in outputs]).mean()
        avg_val_dice = torch.stack([x['val_step_dice'] for x in outputs]).mean()
        tensorboard_logs = {
            "val_loss": outputs[0]['val_step_loss'],  # the outputs is a dict wrapped in a list
            "val_dice": outputs[0]['val_step_dice'],
            "val_IoU": outputs[0]['val_step_IoU'],
            "val_sensitivity": outputs[0]['val_step_sensitivity'],
            "val_specificity": outputs[0]['val_step_specificity']
        }
        return {"val_loss": avg_loss, "val_dice": avg_val_dice, 'log': tensorboard_logs}

    def test_step(self, batch, batch_idx):
        inputs, targets = self._prepare_data(batch)
        # print(f"training input range: {torch.min(inputs)} - {torch.max(inputs)}")
        logits = self(inputs)
        logits = F.interpolate(logits, size=logits.size()[2:])
        probs = torch.sigmoid(logits)
        dice, iou, _, _ = get_score(probs, targets)
        if batch_idx != 0 and batch_idx % 501 == 0:  # save total about 10 picture
            input = inputs.chunk(inputs.size()[0], 0)[0]  # split into 1 in the dimension 0
            target = targets.chunk(targets.size()[0], 0)[0]  # split into 1 in the dimension 0
            logit = probs.chunk(logits.size()[0], 0)[0]  # split into 1 in the dimension 0
            log_all_info(self, input, target, logit, batch_idx, "testing")
        # loss = F.binary_cross_entropy_with_logits(logits, targets)
        loss = dice_loss(probs, targets)
        dice, iou, sensitivity, specificity = get_score(probs, targets)
        return {'test_step_loss': loss,
                'test_step_dice': dice,
                'test_step_IoU': iou,
                'test_step_sensitivity': sensitivity,
                'test_step_specificity': specificity
                }

    def test_epoch_end(self, outputs):
        # torch.stack: Concatenates sequence of tensors along a new dimension.
        avg_loss = torch.stack([x['test_step_loss'] for x in outputs]).mean()
        avg_dice = torch.stack([x['test_step_dice'] for x in outputs]).mean()
        avg_IoU = torch.stack([x['test_step_IoU'] for x in outputs]).mean()
        avg_sensitivity = torch.stack([x['test_step_sensitivity'] for x in outputs]).mean()
        avg_specificity = torch.stack([x['test_step_specificity'] for x in outputs]).mean()
        tqdm_dict = {'test_dice': avg_dice.item()}
        tensorboard_logs = {
            "avg_test_loss": avg_loss,  # the outputs is a dict wrapped in a list
            "avg_test_dice": avg_dice,
            "avg_test_IoU": avg_IoU,
            "avg_test_sensitivity": avg_sensitivity,
            "avg_test_specificity": avg_specificity,
        }
        return {'progress_bar': tqdm_dict, 'log': tensorboard_logs}

    @staticmethod
    def add_model_specific_args(parent_parser: ArgumentParser) -> ArgumentParser:
        """
        parameters defined here will be available to the model through self.hparams
        """
        parser = ArgumentParser(parents=[parent_parser], add_help=False)
        parser.add_argument("--batch_size", type=int, default=2, help='Batch size', dest='batch_size')
        parser.add_argument("--learning_rate", type=float, default=1e-3, help='Learning rate')
        parser.add_argument("--normalization", type=str, default='Group', help='the way of normalization')
        parser.add_argument("--down_sample", type=str, default="max", help="the way to down sample")
        parser.add_argument("--loss", type=str, default="BCEWL", help='Loss Function')
        parser.add_argument("--run", dest='run', type=int, default=1, help='run times')
        return parser