import importlib.util
import io
import json
from pathlib import Path
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('asset_import',Path(__file__).resolve().parents[1]/'import-character-assets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ImportTests(unittest.TestCase):
    def archive(self,extra=None,moc='model.moc3'):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            values={'original/model.model3.json':json.dumps({'FileReferences':{'Moc':moc,'Textures':['texture.png']}}),
                    'original/model.moc3':'synthetic','original/texture.png':'synthetic','original/source.psd':'excluded','original/script.js':'excluded'}
            values.update(extra or {})
            for name,value in values.items():archive.writestr(name,value)
        stream.seek(0)
        return zipfile.ZipFile(stream)
    def test_only_model_assets(self):
        with self.archive() as archive:
            selected,moc,pending=module.plan(archive)
        self.assertEqual(selected,'original/model.model3.json')
        self.assertEqual(moc,'model.moc3')
        self.assertEqual(len(pending),3)
    def test_paths_and_missing_reference(self):
        for extra,moc in [({'../outside.txt':'x'},'model.moc3'),({},'../outside.moc3'),({},'missing.moc3')]:
            with self.archive(extra,moc) as archive,self.assertRaises(ValueError):module.plan(archive)
    def test_multiple_models_require_selection(self):
        with self.archive({'other.model3.json':'{}'}) as archive:
            with self.assertRaises(ValueError):module.plan(archive)
            self.assertEqual(len(module.plan(archive,'original/model.model3.json')[2]),3)
    def test_parent_license_is_preserved(self):
        with self.archive({'Terms of Use.txt':'synthetic terms'}) as archive:
            paths={rel.as_posix() for _,rel in module.plan(archive)[2]}
        self.assertIn('licenses/Terms of Use.txt',paths)

if __name__=='__main__':unittest.main()
