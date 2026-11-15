"""This private companion has no server-side tools or third-party plugins enabled."""


def auto_import_modules(package_name):
    if package_name != "plugins_func.functions":
        raise ValueError("Unexpected plugin package")
    # Upstream eagerly imports every plugin, even with Intent=nointent.
    # Keep the configured no-tool service from loading unrelated integrations.
