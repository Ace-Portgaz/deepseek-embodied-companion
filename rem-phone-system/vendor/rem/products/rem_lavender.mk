# Development product only. Full ROM build and device validation are outstanding.
# The vendor/rem directory must be copied into a complete LineageOS 18.1 tree.
$(call inherit-product, device/xiaomi/lavender/lineage_lavender.mk)

PRODUCT_NAME := rem_lavender
PRODUCT_MODEL := Redmi Note 7
PRODUCT_PACKAGES += RemBody

# The source integration patch removes Quickstep's HOME intent filter only.
# Quickstep remains installed for system recents and navigation services.
# Keep Settings, SystemUI, telephony, recovery and emergency services intact.
# Do not disable SELinux, encryption, lock screen or the permission controller.
# This development product intentionally does not ship API credentials.

