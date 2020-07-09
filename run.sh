#!/bin/bash
#SBATCH --account=def-jlevman
#SBATCH --gres=gpu:v100:4
#SBATCH --nodes=1  # must set 2 if use four than it will stop
#SBATCH --ntasks-per-node=2  # 4 would be more efficient but not working, do not know why
#SBATCH --cpus-per-task=10  #maximum CPU cores per GPU request: 6 on Cedar, 16 on Graham.
#SBATCH --mem=128G   # memory
#SBATCH --output=tune-%j.out  # %N for node name, %j for jobID
#SBATCH --time=03-00:00      # time (DD-HH:MM)
#SBATCH --mail-user=x2019cwn@stfx.ca # used to send email
#SBATCH --mail-type=ALL

module load python/3.6 cuda cudnn gcc/8.3.0

SOURCEDIR=/home/jueqi/scratch

# Prepare virtualenv
#virtualenv --no-download $SLURM_TMPDIR/env
#source $SLURM_TMPDIR/env/bin/activate && echo "$(date +"%T"):  Activated python virtualenv"
source ~/ENV/bin/activate && echo "$(date +"%T"):  Activated python virtualenv"

#echo "$(date +"%T"):  start to install wheels"
#pip install -r $SOURCEDIR/requirements.txt && echo "$(date +"%T"):  install successfully!"

# debugging flags (optional)
export NCCL_DEBUG=INFO
export PYTHONFAULTHANDLER=1
export NCCL_SOCKET_IFNAME=^docker0,lo

echo -e '\n'
cd $SLURM_TMPDIR
mkdir work
# --strip-components prevents making double parent directory
echo "$(date +"%T"):  Copying data"
#tar -xf /home/jueqi/scratch/Data/readable_data.tar -C work && echo "$(date +"%T"):  Copied data"
tar -xf /home/jueqi/scratch/Data/readable_data.tar -C work && echo "$(date +"%T"):  Copied data"
# Now do my computations here on the local disk using the contents of the extracted archive...

cd work
## The computations are done, so clean up the data set...
BATCH_SIZE=4
GPUS=4
NODES=1
LOG_DIR=/home/jueqi/scratch/log
#LOG_DIR=/project/6005889/U-Net_MRI-Data/log

# run script
echo -e '\n\n\n'
#tensorboard --logdir="$LOG_DIR" --host 0.0.0.0 & python3 /home/jueqi/scratch/Unet1/Lit_train.py \
python3 /home/jueqi/scratch/Unet_fine_tune/Lit_train.py \
       --gpus=$GPUS \
       --nodes=$NODES \
       --batch_size=$BATCH_SIZE \
       --name="fine tune" \
       --TensorBoardLogger="$LOG_DIR" \
       --pruning


#python3 /home/jueqi/projects/def-jlevman/jueqi/pytorch_Unet/data/const.py