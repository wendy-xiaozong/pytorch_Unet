import torch
from torchio import AFFINE, DATA, PATH, TYPE, STEM
from data.get_dataset import get_dataset
import warnings
import torchio
import numpy as np
from utils.unet import UNet, UNet3D
from data.const import *
from utils.loss import get_dice_loss
from data.get_datasets import get_dataset
from data.config import Option
import enum
import SimpleITK as sitk
import multiprocessing
import nibabel as nib
from time import ctime
from torchvision.utils import make_grid, save_image
import torch.nn.functional as F
from torchvision.transforms import Resize
import argparse
import logging


# those words used when building the dataset subject
img = "img"
label = "label"
dir_checkpoint = 'checkpoints/'


class Action(enum.Enum):
    TRAIN = 'Training'
    VALIDATE = 'Validation'


def prepare_batch(batch, device):
    inputs = batch[img][DATA].to(device)
    foreground = batch[label][DATA].to(device)
    foreground[foreground > 0.5] = 1
    background = 1 - foreground
    targets = torch.cat((background, foreground), dim=CHANNELS_DIMENSION)
    return inputs, targets


def forward(model, inputs):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        logits = model(inputs)
    return logits


def get_model_and_optimizer(device):
    model = UNet(
        in_channels=1,
        out_classes=2,
        dimensions=3,
        num_encoding_blocks=3,
        out_channels_first_layer=8,
        # normalization='batch',
        upsampling_type='linear',
        padding=True,
        activation='PReLU',
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters())
    return model, optimizer


def run_epoch(epoch_idx, action, loader, model, optimizer):
    is_training = action == Action.TRAIN
    epoch_losses = []
    model.train(is_training)
    for batch_idx, batch in enumerate(loader):
        inputs, targets = prepare_batch(batch, device)
        optimizer.zero_grad()
        with torch.set_grad_enabled(is_training):
            logits = forward(model, inputs)
            probabilities = F.softmax(logits, dim=CHANNELS_DIMENSION)
            batch_losses = get_dice_loss(probabilities, targets)
            batch_loss = batch_losses.mean()
            if is_training:
                batch_loss.backward()
                optimizer.step()
            epoch_losses.append(batch_loss.item())
        print(f'Epoch:  {epoch_idx} | train lose')
    epoch_losses = np.array(epoch_losses)
    print(f'{action.value} mean loss: {epoch_losses.mean():0.3f}')


def train(num_epochs, training_loader, validation_loader, model, optimizer, weights_stem):
    run_epoch(0, Action.VALIDATE, validation_loader, model, optimizer)
    for epoch_idx in range(1, num_epochs + 1):
        print('Starting epoch', epoch_idx)
        run_epoch(epoch_idx, Action.TRAIN, training_loader, model, optimizer)
        run_epoch(epoch_idx, Action.VALIDATE, validation_loader, model, optimizer)
        torch.save(model.state_dict(), f'{weights_stem}_epoch_{epoch_idx}.pth')


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    option = Option()

    device = torch.device('cuda') if torch.cuda.is_available() else 'cpu'
    logging.info(f'Using device {device}')
    CHANNELS_DIMENSION = 1
    SPATIAL_DIMENSIONS = 2, 3, 4

    training_batch_size = 2
    validation_batch_size = 1
    num_epochs = 1000

    datasets = [CC359_DATASET_DIR]
    training_set, validation_set = get_dataset(datasets)

    training_loader = torch.utils.data.DataLoader(
        training_set,
        batch_size=training_batch_size,
        shuffle=True,
        num_workers=multiprocessing.cpu_count(),
        # num_workers=0,
    )

    validation_loader = torch.utils.data.DataLoader(
        validation_set,
        batch_size=validation_batch_size,
        num_workers=multiprocessing.cpu_count(),
        # num_workers=0,
    )

    model, optimizer = get_model_and_optimizer(device)
    logging.info(f'Network:\n'
                 f'\t{model.n_channels} input channels\n'
                 f'\t{model.n_classes} output channels (classes)\n')

    # if args.load:
    #     net.load_state_dict(
    #         torch.load(args.load, map_location=device)
    #     )
    #     logging.info(f'Model loaded from {args.load}')


    weights_stem = 'whole_images'
    train(num_epochs, training_loader, validation_loader, model, optimizer, weights_stem)

    batch = next(iter(validation_loader))
    model.eval()
    inputs, targets = prepare_batch(batch, device)
    with torch.no_grad():
        logits = forward(model, inputs)

