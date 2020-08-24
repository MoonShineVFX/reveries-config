import re
from pxr import Usd, Sdf, UsdGeom

from avalon import io, api


def _get_variant_data(asset_name, prim_type='default'):
    """
    Get variant data
    :param asset_name: Asset name. eg.'HanMaleA'
    :return:
    variant_data = {
        'lookDefault': [
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\modelDefault\v003\geom.usda',
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\lookDefault\v002\assign.usda',
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\lookDefault\v002\look.usda'
        ],
        'lookClothesB': [
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\modelDefault\v003\geom.usda',
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\lookClothesB\v002\assign.usda',
            r'F:\usd\test\data\OCEAN\Character\HanMaleA\publish\lookClothesB\v002\look.usda'
        ]
    }
    variant_key = ['lookDefault', 'lookClothesB']
    """
    from reveries.new_utils import get_publish_files

    filter = {"type": "asset", "name": asset_name}
    asset_data = io.find_one(filter)
    asset_id = asset_data['_id']

    # Get lookdev subset without lookProxy subset
    variant_key = []  # ['lookDefault', 'lookClothesB']
    filter = {
        "type": "subset",
        "parent": io.ObjectId(str(asset_id)),
        "name": re.compile("look*")
    }
    # subset_data = []
    subset_data = [subset for subset in io.find(filter)]
    for subset in io.find(filter):
        regex = re.compile("^.*?(?<!Proxy)$")
        _subset_name = subset['name']
        if regex.search(_subset_name):
            # subset_data.append(subset)
            variant_key.append(_subset_name)  #

    # Get assign/look usd file
    lookfiles_data = {}
    for _subset in subset_data:
        subset_name = _subset['name']
        subset_id = _subset['_id']
        files = get_publish_files.get_files(subset_id)
        lookfiles_data[subset_name] = files.get('USD', {})

    return lookfiles_data, variant_key


def _get_geom_usd(asset_name):
    from reveries.new_utils import get_publish_files

    filter = {"type": "asset", "name": asset_name}
    asset_data = io.find_one(filter)
    asset_id = asset_data['_id']

    filter = {
        "type": "subset",
        "parent": io.ObjectId(str(asset_id)),
        "name": 'modelDefault'
    }
    model_data = io.find_one(filter)

    files = get_publish_files.get_files(model_data['_id']).get('USD', [])

    return files[0] if files else ''


def prim_export(asset_name, output_path, prim_type='default'):
    # Get variant data
    variant_data, variant_key = _get_variant_data(asset_name, prim_type=prim_type)
    assert variant_data, "No variant found from publish."

    # Check prim name
    if prim_type == 'proxy':
        prim_name = 'modelDefaultProxy'
    else:
        prim_name = 'modelDefault'

    # Get model usd file
    geom_file_path = _get_geom_usd(asset_name)

    # Create USD file
    stage = Usd.Stage.CreateInMemory()
    root_define = UsdGeom.Xform.Define(stage, "/ROOT")

    variants = root_define.GetPrim().GetVariantSets().AddVariantSet("appearance")

    # Get default look option name
    default_key = ''
    for _key in variant_data.keys():
        match = re.findall('(\S+default)', _key.lower())
        if match:
            default_key = _key
    default_key = default_key or variant_data.keys()[0]

    for _key in variant_key:
        if prim_type == 'proxy':
            usd_file_paths = variant_data.get('{}Proxy'.format(_key), [])
            if not usd_file_paths:
                usd_file_paths = variant_data.get('lookDefaultProxy', [])
        else:
            usd_file_paths = variant_data.get(_key, [])
        # print _key, usd_file_paths
        variants.AddVariant(_key)
        variants.SetVariantSelection(_key)

        #
        with variants.GetVariantEditContext():
            # Add step variants
            variant_define = UsdGeom.Xform.Define(stage, "/ROOT/{}".format(prim_name))
            if prim_type == 'proxy':
                variant_define.CreatePurposeAttr('proxy')
            else:
                variant_define.CreatePurposeAttr('render')

            _prim = stage.GetPrimAtPath("/ROOT/{}".format(prim_name))
            _usd_paths = [
                Sdf.Reference(geom_file_path)
            ]
            for ref_path in usd_file_paths:
                _usd_paths.append(Sdf.Reference(ref_path))

            _prim.GetReferences().SetReferences(_usd_paths)

    variants.SetVariantSelection(default_key)

    # Set default prim
    rootPrim = stage.GetPrimAtPath('/ROOT')
    stage.SetDefaultPrim(rootPrim)

    # print(stage.GetRootLayer().ExportToString())
    stage.GetRootLayer().Export(output_path)
