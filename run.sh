#!/bin/bash
#SBATCH --gres=gpu:t4:4  # request GPU "generic resource"
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=4  #maximum CPU cores per GPU request: 6 on Cedar, 16 on Graham.
#SBATCH --mem=170G   # memory
#SBATCH --output=try1-%j.out  # %N for node name, %j for jobID
#SBATCH --time=03-00:00      # time (DD-HH:MM)
#SBATCH --mail-user=x2019cwn@stfx.ca # used to send email
#SBATCH --mail-type=ALL
#SBATCH --signal=SIGUSR1@90

module load python/3.6
source ~/ENV/bin/activate && echo "$(date +"%T"):  Activated python virtualenv"
pip3 install --user opencv-python # install opencv
pip3 install nilearn
pip3 install sklearn

echo -e '\n'
cd $SLURM_TMPDIR
mkdir work
# --strip-components prevents making double parent directory
echo "$(date +"%T"):  Copying data"
tar -xf /project/6005889/U-Net_MRI-Data/readable_data.tar -C work && echo "$(date +"%T"):  Copied data"
# Now do my computations here on the local disk using the contents of the extracted archive...
cd work
## The computations are done, so clean up the data set...

RUN=1
BATCH_SIZE=4
GPUS=4
LOG_DIR=/home/$USER/projects/def-jlevman/U-Net_MRI-Data/log

# run script
echo -e '\n\n\n'
tensorboard --logdir="$LOG_DIR" --host 0.0.0.0 & python3 /home/jueqi/projects/def-jlevman/jueqi/Unet1/Lit_train.py \
       --gpus="$GPUS" \
       --batch_size=$BATCH_SIZE \
       --run=$RUN \
       --name="using dice loss" \
       --TensorBoardLogger="$LOG_DIR"


#python3 /home/jueqi/projects/def-jlevman/jueqi/pytorch_Unet/data/const.py