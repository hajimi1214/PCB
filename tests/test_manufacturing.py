import sys
from pathlib import Path
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from manufacturing import ManufacturingError,validate_bom_xlsx,validate_gerber_zip,validate_pick_and_place_tsv


class ManufacturingValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_gerber_requires_four_copper_layers_outline_drill_and_valid_crc(self):
        path=self.root/'Gerber.zip'
        with zipfile.ZipFile(path,'w') as archive:
            for name in ('Top.GTL','Bottom.GBL','Inner1.G1','Inner2.G2'):
                archive.writestr(name,'%TF.FileFunction,Copper,L1,Top*%\nM02*\n')
            archive.writestr('Outline.GKO','%TF.FileFunction,Profile*%\nM02*\n')
            archive.writestr('Drill.PTH.DRL','M48\nM30\n')
        result=validate_gerber_zip(path)
        self.assertEqual(result['copper_layer_count'],4)
        self.assertTrue(result['outline_present'])
        self.assertTrue(result['drill_present'])

    def test_gerber_missing_inner_layer_is_rejected(self):
        path=self.root/'Gerber.zip'
        with zipfile.ZipFile(path,'w') as archive:
            for name in ('Top.GTL','Bottom.GBL','Inner1.G1'):
                archive.writestr(name,'M02*')
            archive.writestr('Outline.GKO','M02*')
            archive.writestr('Drill.DRL','M48\nM30')
        with self.assertRaises(ManufacturingError):validate_gerber_zip(path)

    def test_bom_requires_readable_xlsx_with_data_rows(self):
        path=self.root/'BOM.xlsx'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types/>')
            archive.writestr('xl/workbook.xml','<workbook/>')
            archive.writestr('xl/worksheets/sheet1.xml','<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Designator</t></is></c><c r="B1" t="inlineStr"><is><t>Qty</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>U1</t></is></c><c r="B2"><v>1</v></c></row></sheetData></worksheet>')
        self.assertEqual(validate_bom_xlsx(path)['component_reference_count'],1)

    def test_bom_rejects_quantity_that_does_not_match_designators(self):
        path=self.root/'BOM.xlsx'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types/>')
            archive.writestr('xl/workbook.xml','<workbook/>')
            archive.writestr('xl/worksheets/sheet1.xml','<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Designator</t></is></c><c r="B1" t="inlineStr"><is><t>Qty</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>U1,U2</t></is></c><c r="B2"><v>1</v></c></row></sheetData></worksheet>')
        with self.assertRaises(ManufacturingError):validate_bom_xlsx(path)

    def test_pick_and_place_requires_utf16le_tabular_rows(self):
        path=self.root/'PickAndPlace.tsv'
        path.write_bytes(b'\xff\xfe'+'Reference\tX\tY\tRotation\tLayer\nU1\t1\t2\t0\tTop\n'.encode('utf-16le'))
        result=validate_pick_and_place_tsv(path)
        self.assertEqual(result['encoding'],'UTF-16LE')
        self.assertEqual(result['delimiter'],'TAB')
        self.assertEqual(result['component_count'],1)

    def test_pick_and_place_rejects_unknown_side_or_duplicate_reference(self):
        path=self.root/'PickAndPlace.tsv'
        path.write_bytes(b'\xff\xfe'+'Reference\tX\tY\tRotation\tLayer\nU1\t1\t2\t0\tUnknown\n'.encode('utf-16le'))
        with self.assertRaises(ManufacturingError):validate_pick_and_place_tsv(path)
        path.write_bytes(b'\xff\xfe'+'Reference\tX\tY\tRotation\tLayer\nU1\t1\t2\t0\tTop\nU1\t2\t3\t90\tBottom\n'.encode('utf-16le'))
        with self.assertRaises(ManufacturingError):validate_pick_and_place_tsv(path)


if __name__=='__main__':unittest.main()
