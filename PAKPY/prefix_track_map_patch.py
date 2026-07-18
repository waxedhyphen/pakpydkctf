import anim_packed_sample_decode as packed_patch
import anim_tf_codec_patch as tf_patch


def install(App):
    # Keep the former heuristic output available for diagnostics. The TF codec
    # replaces it only when a stream layout has been verified.
    packed_patch.install_into()
    tf_patch.install_into()
