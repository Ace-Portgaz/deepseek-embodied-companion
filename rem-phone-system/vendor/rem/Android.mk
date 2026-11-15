# Rebuild the separate DTBO image when the Rem lavender overlay changes.
# The upstream image rule only depends on tools, so an incremental build can
# otherwise package the previous overlay even after the kernel rebuilds it.
ifeq ($(TARGET_PRODUCT),rem_lavender)
ifeq ($(strip $(BOARD_PREBUILT_DTBOIMAGE)),)
$(error Rem lavender requires the configured separate DTBO image target)
endif
$(BOARD_PREBUILT_DTBOIMAGE): $(TARGET_KERNEL_SOURCE)/arch/arm/boot/dts/qcom/sdm660-mtp-lavender-overlay.dts
endif
