#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import numpy as np
import matplotlib.pyplot as plt

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

import tensorflow_addons as tfa
import tensorflow_datasets as tfds
from sklearn.utils import shuffle
from PIL import Image

# Note that you must have Tensorflow >= 2.5.0
print(tf.version.VERSION)

tfds.disable_progress_bar()
autotune = tf.data.AUTOTUNE


# # Define Parameters

# In[2]:


# Tuple defining dimensions to resize the dataset to during preprocessing
dataset_dimensions = (256, 256)

# File path pointing to H5 model saved during training process
model_path = r"C:\Users\Vee\Desktop\python\GAN\CYCLEGAN\satelite2map\model_27.h5"

# File path pointing to folder where generated results are saved
results_save_path = r"C:\Users\Vee\Desktop\python\GAN\CYCLEGAN\Results"


# # Define Dataset Source

# In[3]:


# Boolean flag for if you want to train with a preprocessed TensorFlow Dataset
preprocessed_dataset = False

# Dataset names can be found at https://www.tensorflow.org/datasets/catalog/cycle_gan
if(preprocessed_dataset):
    # WARNING: Downloading of certain datasets is currently bugged on Tensorflow
    # https://github.com/tensorflow/tensorflow/issues/31171
    # https://stackoverflow.com/questions/69866596/how-to-download-dataset-from-tensorflow-dataset-locally
    dataset_name = "cycle_gan/apple2orange"

# If you want to train with your own dataset
# Set preprocessed_dataset to False and provide the folder file paths of your input and output datasets
else:
    # File path pointing to folder containing input dataset if not using preprocessed dataset
    input_path = r'C:\Users\Vee\Desktop\python\GAN\CYCLEGAN\maps\maps\trainA'

    # File path pointing to folder containing output dataset if not using preprocessed dataset
    output_path = r'C:\Users\Vee\Desktop\python\GAN\CYCLEGAN\maps\maps\trainB'


# # Define Image Preprocessing Functions

# In[4]:


def normalize_img(img):
    img = tf.cast(img, dtype=tf.float32)
    # Map values in the range [-1, 1]
    return (img / 127.5) - 1.0

def preprocess_train_image(img, label):
    # Random flip
    img = tf.image.random_flip_left_right(img)
    # Resize to the original size first
    img = tf.image.resize(img, [*dataset_dimensions])
    # Normalize the pixel values in the range [-1, 1]
    img = normalize_img(img)
    return img

def preprocess_test_image(img, label):
    # Only resizing and normalization for the test images.
    img = tf.image.resize(img, [dataset_dimensions[0], dataset_dimensions[1]])
    img = normalize_img(img)
    return img

# load data from specified file path 
def load_data():

    # Initializing arrays for data and image file paths
    src_x = []
    src_y = []
    dst_x = []
    dst_y = []
    paths = []
    
    # Get the file paths of all image files in this folder
    for r, d, f in os.walk(input_path):
        for file in f:
            if '.jpg' in file or 'png' in file:
                paths.append(os.path.join(r, file))

    # For each file add input style image to array
    for path in paths:
        img = Image.open(path)

        # Remove PNG alpha layer
        x = np.array(img)
        x = x[...,:3]
        
        # If image does not have 3 RGB channels then don't add it to the dataset
        try:
            if(len(x.shape) == 3):
                if(x.shape[2] == 3):
                    # Add input image
                    src_x.append(x)

                    # Add label of 0 to input image
                    src_y.append(0)
        except:
            print(x.shape)
            
    # Reset paths array for output images file paths
    paths = []

    # Get the file paths of all image files in this folder
    for r, d, f in os.walk(output_path):
        for file in f:
            if '.jpg' in file or 'png' in file:
                paths.append(os.path.join(r, file))

    # For each file add output style image to array
    for path in paths:
        img = Image.open(path)

        # Remove PNG alpha layer
        y = np.array(img)
        y = y[...,:3]
        
        # If image does not have 3 RGB channels then don't add it to the dataset
        try:
            if(len(y.shape) == 3):
                if(y.shape[2] == 3):
                    # Add output image
                    dst_x.append(y)

                    # Add label of 0 to output image
                    dst_y.append(1)
        except:
            print(y.shape)

    # Return x_train and y_train for both datasets
    return np.array(src_x), np.array(src_y), np.array(dst_x), np.array(dst_y)


# # Preprocess Dataset

# In[5]:


# If training with a preprocessed TensorFlow Dataset
if(preprocessed_dataset):
    # Load the preprocessed Tensorflow dataset using tensorflow-datasets.
    dataset, _ = tfds.load(dataset_name, with_info=True, as_supervised=True)
    train_src, train_dst = dataset["trainA"], dataset["trainB"]
    test_src, test_dst = dataset["testA"], dataset["testB"]

# If training with your own dataset then process the data manually
else:
    # Load the dataset into NumPy arrays
    src_X, src_Y, dst_X, dst_Y = load_data()
    
    # Load the NumPy arrays into TensorFlow Dataset objects
    test_src = tf.data.Dataset.from_tensor_slices((src_X[0:(len(src_X) - 1)], src_Y[0:(len(src_Y) - 1)]))
    test_dst = tf.data.Dataset.from_tensor_slices((dst_X[0:(len(dst_X) - 1)], dst_Y[0:(len(dst_Y) - 1)]))

# Apply the preprocessing operations to the test data
test_src = (test_src.map(preprocess_test_image, num_parallel_calls=autotune).cache().shuffle(256).batch(4))
test_dst = (test_dst.map(preprocess_test_image, num_parallel_calls=autotune).cache().shuffle(256).batch(4))


# # Define CycleGAN Class Building Blocks

# In[6]:


# Weights initializer for the layers.
kernel_init = keras.initializers.RandomNormal(mean=0.0, stddev=0.02)

# Gamma initializer for instance normalization.
gamma_init = keras.initializers.RandomNormal(mean=0.0, stddev=0.02)

class ReflectionPadding2D(layers.Layer):
    """Implements Reflection Padding as a layer.
    Args:
        padding(tuple): Amount of padding for the
        spatial dimensions.
    Returns:
        A padded tensor with the same type as the input tensor.
    """

    def __init__(self, padding=(1, 1), **kwargs):
        self.padding = tuple(padding)
        super(ReflectionPadding2D, self).__init__(**kwargs)

    def call(self, input_tensor, mask=None):
        padding_width, padding_height = self.padding
        padding_tensor = [
            [0, 0],
            [padding_height, padding_height],
            [padding_width, padding_width],
            [0, 0],
        ]
        return tf.pad(input_tensor, padding_tensor, mode="REFLECT")


def residual_block(
    x,
    activation,
    kernel_initializer=kernel_init,
    kernel_size=(3, 3),
    strides=(1, 1),
    padding="valid",
    gamma_initializer=gamma_init,
    use_bias=False,
):
    dim = x.shape[-1]
    input_tensor = x

    x = ReflectionPadding2D()(input_tensor)
    x = layers.Conv2D(
        dim,
        kernel_size,
        strides=strides,
        kernel_initializer=kernel_initializer,
        padding=padding,
        use_bias=use_bias,
    )(x)
    x = tfa.layers.InstanceNormalization(gamma_initializer=gamma_initializer)(x)
    x = activation(x)

    x = ReflectionPadding2D()(x)
    x = layers.Conv2D(
        dim,
        kernel_size,
        strides=strides,
        kernel_initializer=kernel_initializer,
        padding=padding,
        use_bias=use_bias,
    )(x)
    x = tfa.layers.InstanceNormalization(gamma_initializer=gamma_initializer)(x)
    x = layers.add([input_tensor, x])
    return x


def downsample(
    x,
    filters,
    activation,
    kernel_initializer=kernel_init,
    kernel_size=(3, 3),
    strides=(2, 2),
    padding="same",
    gamma_initializer=gamma_init,
    use_bias=False,
):
    x = layers.Conv2D(
        filters,
        kernel_size,
        strides=strides,
        kernel_initializer=kernel_initializer,
        padding=padding,
        use_bias=use_bias,
    )(x)
    x = tfa.layers.InstanceNormalization(gamma_initializer=gamma_initializer)(x)
    if activation:
        x = activation(x)
    return x


def upsample(
    x,
    filters,
    activation,
    kernel_size=(3, 3),
    strides=(2, 2),
    padding="same",
    kernel_initializer=kernel_init,
    gamma_initializer=gamma_init,
    use_bias=False,
):
    x = layers.Conv2DTranspose(
        filters,
        kernel_size,
        strides=strides,
        padding=padding,
        kernel_initializer=kernel_initializer,
        use_bias=use_bias,
    )(x)
    x = tfa.layers.InstanceNormalization(gamma_initializer=gamma_initializer)(x)
    if activation:
        x = activation(x)
    return x

"""
## Build the generators
The generator consists of downsampling blocks: nine residual blocks
and upsampling blocks. The structure of the generator is the following:
```
c7s1-64 ==> Conv block with `relu` activation, filter size of 7
d128 ====|
         |-> 2 downsampling blocks
d256 ====|
R256 ====|
R256     |
R256     |
R256     |
R256     |-> 9 residual blocks
R256     |
R256     |
R256     |
R256 ====|
u128 ====|
         |-> 2 upsampling blocks
u64  ====|
c7s1-3 => Last conv block with `tanh` activation, filter size of 7.
```
"""


def get_resnet_generator(
    filters=64,
    num_downsampling_blocks=2,
    num_residual_blocks=9,
    num_upsample_blocks=2,
    gamma_initializer=gamma_init,
    name=None,
):
    img_input = layers.Input(shape=(dataset_dimensions[0], dataset_dimensions[1], 3), name=name + "_img_input")
    x = ReflectionPadding2D(padding=(3, 3))(img_input)
    x = layers.Conv2D(filters, (7, 7), kernel_initializer=kernel_init, use_bias=False)(
        x
    )
    x = tfa.layers.InstanceNormalization(gamma_initializer=gamma_initializer)(x)
    x = layers.Activation("relu")(x)

    # Downsampling
    for _ in range(num_downsampling_blocks):
        filters *= 2
        x = downsample(x, filters=filters, activation=layers.Activation("relu"))

    # Residual blocks
    for _ in range(num_residual_blocks):
        x = residual_block(x, activation=layers.Activation("relu"))

    # Upsampling
    for _ in range(num_upsample_blocks):
        filters //= 2
        x = upsample(x, filters, activation=layers.Activation("relu"))

    # Final block
    x = ReflectionPadding2D(padding=(3, 3))(x)
    x = layers.Conv2D(3, (7, 7), padding="valid")(x)
    x = layers.Activation("tanh")(x)

    model = keras.models.Model(img_input, x, name=name)
    return model


"""
## Build the discriminators
The discriminators implement the following architecture:
`C64->C128->C256->C512`
"""


def get_discriminator(
    filters=64, kernel_initializer=kernel_init, num_downsampling=3, name=None
):
    img_input = layers.Input(shape=(dataset_dimensions[0], dataset_dimensions[1], 3), name=name + "_img_input")
    x = layers.Conv2D(
        filters,
        (4, 4),
        strides=(2, 2),
        padding="same",
        kernel_initializer=kernel_initializer,
    )(img_input)
    x = layers.LeakyReLU(0.2)(x)

    num_filters = filters
    for num_downsample_block in range(3):
        num_filters *= 2
        if num_downsample_block < 2:
            x = downsample(
                x,
                filters=num_filters,
                activation=layers.LeakyReLU(0.2),
                kernel_size=(4, 4),
                strides=(2, 2),
            )
        else:
            x = downsample(
                x,
                filters=num_filters,
                activation=layers.LeakyReLU(0.2),
                kernel_size=(4, 4),
                strides=(1, 1),
            )

    x = layers.Conv2D(
        1, (4, 4), strides=(1, 1), padding="same", kernel_initializer=kernel_initializer
    )(x)

    model = keras.models.Model(inputs=img_input, outputs=x, name=name)
    return model

# Get the generators
gen_G = get_resnet_generator(name="generator_G")
gen_F = get_resnet_generator(name="generator_F")

# Get the discriminators
disc_X = get_discriminator(name="discriminator_X")
disc_Y = get_discriminator(name="discriminator_Y")

"""
## Build the CycleGAN model
We will override the `train_step()` method of the `Model` class
for training via `fit()`.
"""
class CycleGan(keras.Model):
    def __init__(
        self,
        generator_G,
        generator_F,
        discriminator_X,
        discriminator_Y,
        lambda_cycle=10.0,
        lambda_identity=0.5,
    ):
        super(CycleGan, self).__init__()
        self.gen_G = generator_G
        self.gen_F = generator_F
        self.disc_X = discriminator_X
        self.disc_Y = discriminator_Y
        self.lambda_cycle = lambda_cycle
        self.lambda_identity = lambda_identity

    def compile(
        self,
        gen_G_optimizer,
        gen_F_optimizer,
        disc_X_optimizer,
        disc_Y_optimizer,
        gen_loss_fn,
        disc_loss_fn,
    ):
        super(CycleGan, self).compile()
        self.gen_G_optimizer = gen_G_optimizer
        self.gen_F_optimizer = gen_F_optimizer
        self.disc_X_optimizer = disc_X_optimizer
        self.disc_Y_optimizer = disc_Y_optimizer
        self.generator_loss_fn = gen_loss_fn
        self.discriminator_loss_fn = disc_loss_fn
        self.cycle_loss_fn = keras.losses.MeanAbsoluteError()
        self.identity_loss_fn = keras.losses.MeanAbsoluteError()

    def train_step(self, batch_data):
        # Get batch dataset for current training step
        real_x, real_y = batch_data

        # For CycleGAN, we need to calculate different
        # kinds of losses for the generators and discriminators.
        # We will perform the following steps here:
        #
        # 1. Pass real images through the generators and get the generated images
        # 2. Pass the generated images back to the generators to check if we
        #    we can predict the original image from the generated image.
        # 3. Do an identity mapping of the real images using the generators.
        # 4. Pass the generated images in 1) to the corresponding discriminators.
        # 5. Calculate the generators total loss (adverserial + cycle + identity)
        # 6. Calculate the discriminators loss
        # 7. Update the weights of the generators
        # 8. Update the weights of the discriminators
        # 9. Return the losses in a dictionary

        with tf.GradientTape(persistent=True) as tape:
            # Generate a set of fake src -> dst style images
            fake_y = self.gen_G(real_x, training=True)
            # Generate a set of fake dst -> src style images
            fake_x = self.gen_F(real_y, training=True)

            # Cycle src -> dst -> src
            cycled_x = self.gen_F(fake_y, training=True)
            # Cycle dst -> src -> dst
            cycled_y = self.gen_G(fake_x, training=True)

            # Identity mapping
            same_x = self.gen_F(real_x, training=True)
            same_y = self.gen_G(real_y, training=True)

            # Discriminator output
            disc_real_x = self.disc_X(real_x, training=True)
            disc_fake_x = self.disc_X(fake_x, training=True)

            disc_real_y = self.disc_Y(real_y, training=True)
            disc_fake_y = self.disc_Y(fake_y, training=True)

            # Generator adverserial loss
            gen_G_loss = self.generator_loss_fn(disc_fake_y)
            gen_F_loss = self.generator_loss_fn(disc_fake_x)

            # Generator cycle loss
            cycle_loss_G = self.cycle_loss_fn(real_y, cycled_y) * self.lambda_cycle
            cycle_loss_F = self.cycle_loss_fn(real_x, cycled_x) * self.lambda_cycle

            # Generator identity loss
            id_loss_G = (
                self.identity_loss_fn(real_y, same_y)
                * self.lambda_cycle
                * self.lambda_identity
            )
            id_loss_F = (
                self.identity_loss_fn(real_x, same_x)
                * self.lambda_cycle
                * self.lambda_identity
            )

            # Total generator loss
            total_loss_G = gen_G_loss + cycle_loss_G + id_loss_G
            total_loss_F = gen_F_loss + cycle_loss_F + id_loss_F

            # Discriminator loss
            disc_X_loss = self.discriminator_loss_fn(disc_real_x, disc_fake_x)
            disc_Y_loss = self.discriminator_loss_fn(disc_real_y, disc_fake_y)

        # Get the gradients for the generators
        grads_G = tape.gradient(total_loss_G, self.gen_G.trainable_variables)
        grads_F = tape.gradient(total_loss_F, self.gen_F.trainable_variables)

        # Get the gradients for the discriminators
        disc_X_grads = tape.gradient(disc_X_loss, self.disc_X.trainable_variables)
        disc_Y_grads = tape.gradient(disc_Y_loss, self.disc_Y.trainable_variables)

        # Update the weights of the generators
        self.gen_G_optimizer.apply_gradients(
            zip(grads_G, self.gen_G.trainable_variables)
        )
        self.gen_F_optimizer.apply_gradients(
            zip(grads_F, self.gen_F.trainable_variables)
        )

        # Update the weights of the discriminators
        self.disc_X_optimizer.apply_gradients(
            zip(disc_X_grads, self.disc_X.trainable_variables)
        )
        self.disc_Y_optimizer.apply_gradients(
            zip(disc_Y_grads, self.disc_Y.trainable_variables)
        )

        return {
            "G_loss": total_loss_G,
            "F_loss": total_loss_F,
            "D_X_loss": disc_X_loss,
            "D_Y_loss": disc_Y_loss,
        }

# Loss function for evaluating adversarial loss
adv_loss_fn = keras.losses.MeanSquaredError()

# Define the loss function for the generators
def generator_loss_fn(fake):
    fake_loss = adv_loss_fn(tf.ones_like(fake), fake)
    return fake_loss

# Define the loss function for the discriminators
def discriminator_loss_fn(real, fake):
    real_loss = adv_loss_fn(tf.ones_like(real), real)
    fake_loss = adv_loss_fn(tf.zeros_like(fake), fake)
    return (real_loss + fake_loss) * 0.5


# # Instantiate Empty CycleGAN Model To Load Weights Into

# In[7]:


# Create empty cycle gan model
cycle_gan_load = CycleGan(generator_G=gen_G, generator_F=gen_F, discriminator_X=disc_X, discriminator_Y=disc_Y)

# Compile the model
cycle_gan_load.compile(
    gen_G_optimizer=keras.optimizers.Adam(learning_rate=2e-4, beta_1=0.5),
    gen_F_optimizer=keras.optimizers.Adam(learning_rate=2e-4, beta_1=0.5),
    disc_X_optimizer=keras.optimizers.Adam(learning_rate=2e-4, beta_1=0.5),
    disc_Y_optimizer=keras.optimizers.Adam(learning_rate=2e-4, beta_1=0.5),
    gen_loss_fn=generator_loss_fn,
    disc_loss_fn=discriminator_loss_fn,
)

# Set model is built flag
cycle_gan_load.built = True


# # Load Weights Into Model

# In[8]:


# Load weights saved from training
cycle_gan_load.load_weights(model_path)


# # Perform A To B Inference On Trained Model

# In[15]:


fig, ax = plt.subplots(4, 2, figsize=(10, 15))
# Perform inference on 4 random points from the train dataset
for i, img in enumerate(test_src.take(4)):
    prediction = cycle_gan_load.gen_G(img, training=False)[0].numpy()
    prediction = (prediction * 127.5 + 127.5).astype(np.uint8)
    img = (img[0] * 127.5 + 127.5).numpy().astype(np.uint8)

    ax[i, 0].imshow(img)
    ax[i, 1].imshow(prediction)
    ax[i, 0].set_title("Input Image")
    ax[i, 0].set_title("Input Image")
    ax[i, 1].set_title("Translated Image")
    ax[i, 0].axis("off")
    ax[i, 1].axis("off")

    prediction = keras.preprocessing.image.array_to_img(prediction)
    
plt.tight_layout()
plt.show()
# Save figure to .png image in specified folder
fig.savefig(results_save_path + "\\generated_sample_A2B.png")


# # Perform B To A Inference On Trained Model

# In[12]:


fig, ax = plt.subplots(4, 2, figsize=(10, 15))
# Perform inference on 4 random points from the train dataset
for i, img in enumerate(test_dst.take(4)):
    prediction = cycle_gan_load.gen_F(img, training=False)[0].numpy()
    prediction = (prediction * 127.5 + 127.5).astype(np.uint8)
    img = (img[0] * 127.5 + 127.5).numpy().astype(np.uint8)

    ax[i, 0].imshow(img)
    ax[i, 1].imshow(prediction)
    ax[i, 0].set_title("Input Image")
    ax[i, 0].set_title("Input Image")
    ax[i, 1].set_title("Translated Image")
    ax[i, 0].axis("off")
    ax[i, 1].axis("off")

    prediction = keras.preprocessing.image.array_to_img(prediction)
    
plt.tight_layout()
plt.show()
# Save figure to .png image in specified folder
fig.savefig(results_save_path + "\\generated_sample_B2A.png")

