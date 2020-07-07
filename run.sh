#!/bin/bash
#SBATCH --account=def-jlevman
#SBATCH --gres=gpu:t4:2  # request GPU "generic resource", on Graham
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=4  #maximum CPU cores per GPU request: 6 on Cedar, 16 on Graham.
#SBATCH --mem=64G   # memory
#SBATCH --output=cropped-%j.out  # %N for node name, %j for jobID
#SBATCH --time=00-03:00      # time (DD-HH:MM)
#SBATCH --mail-user=x2019cwn@stfx.ca # used to send email
#SBATCH --mail-type=ALL

module load python/3.6 cuda cudnn

SOURCEDIR=/home/jueqi/scratch

# Prepare virtualenv
#virtualenv --no-download $SLURM_TMPDIR/env && echo "$(date +"%T"):  Activated python virtualenv"
#source $SLURM_TMPDIR/env/bin/activate
#pip install --no-index -r $SOURCEDIR/requirements.txt
source ~/ENV/bin/activate && echo "$(date +"%T"):  Activated python virtualenv"


echo -e '\n'
cd $SLURM_TMPDIR
mkdir work
# --strip-components prevents making double parent directory
echo "$(date +"%T"):  Copying data"
# tar -xf /home/jueqi/scratch/Data/readable_data.tar -C work && echo "$(date +"%T"):  Copied data"
tar -xf /project/6005889/U-Net_MRI-Data/cropped_data.tar -C work && echo "$(date +"%T"):  Copied data"
# Now do my computations here on the local disk using the contents of the extracted archive...
## The computations are done, so clean up the data set...

RUN=1
BATCH_SIZE=2
GPUS=2
LOG_DIR=/project/6005889/U-Net_MRI-Data/log

# run script
echo -e '\n\n\n'
tensorboard --logdir="$LOG_DIR" --host 0.0.0.0 & python3 /home/jueqi/projects/def-jlevman/jueqi/Unet1/Lit_train.py \
       --gpus="$GPUS" \
       --batch_size=$BATCH_SIZE \
       --run=$RUN \
       --name="using cropped data, flipping in 3 dimension" \
       --TensorBoardLogger="$LOG_DIR"


#python3 /home/jueqi/projects/def-jlevman/jueqi/pytorch_Unet/data/const.py