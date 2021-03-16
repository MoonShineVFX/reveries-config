import os

from pxr import Usd, UsdGeom, UsdShade

# import numpy as np


def stripPathNamespace(path):
    return '/'.join([x.split(':')[-1] for x in path.split('|')])


def keepPathNamespace(path):
    return '/'.join([x.replace(':', '_') for x in path.split('|')])


def stripNamespace(name):
    return name.split(':')[-1]


def keepNamespace(name):
    return name.replace(':', '_')


def _checkActive(path):
    import maya.cmds as cmds

    maya_path = path.replace('/', '|')
    if cmds.objExists(maya_path):
        # if maya_path.hasAttr('intermediateObject'):
        if cmds.attributeQuery('intermediateObject', node=maya_path, ex=True):
            # if maya_path.getAttr('intermediateObject'):
            if cmds.getAttr('{}.intermediateObject'.format(maya_path)):
                return False

        return cmds.getAttr('{}.v'.format(maya_path))
    else:
        return True


def export(dagObject, merge=False, scopeName='Looks', purpose='all',
           assetVersion=None, assetName=None, stripNS=True,
           transformAssign=False, out_path='', force=False):
    """
    transformAssign not works when face-assign
    """
    import maya.api.OpenMaya as om
    import maya.cmds as cmds

    if not dagObject or not out_path:
        return

    # Check root node is top node
    parent_node = None
    if not force:
        parent_node = cmds.listRelatives(dagObject, allParents=True)
        if parent_node:
            cmds.select(dagObject)
            cmds.parent(w=True)
            cmds.select(cl=True)

    # Start export
    shapeChildren = cmds.listRelatives(dagObject, ad=True, f=True, typ='shape')

    if stripNS is True:
        procNamespace = stripNamespace
        procPathNamespace = stripPathNamespace
    else:
        procNamespace = keepNamespace
        procPathNamespace = keepPathNamespace

    if purpose == 'preview':
        materialPurpose = UsdShade.Tokens.preview
    elif purpose == 'full':
        materialPurpose = UsdShade.Tokens.full
    else:
        materialPurpose = UsdShade.Tokens.allPurpose

    omList = om.MSelectionList()
    for shape in shapeChildren:
        omList.add(shape)

    stage = Usd.Stage.CreateInMemory()

    meshList = [om.MFnMesh(omList.getDagPath(i)) for i in range(omList.length())]

    for i, mesh in zip(range(omList.length()), meshList):
        path = omList.getDagPath(i).fullPathName()

        if cmds.objectType(path) != "mesh":
            continue

        if cmds.attributeQuery('intermediateObject', node=path, ex=True):
            if cmds.getAttr("{}.intermediateObject".format(path)):
                continue

        if merge is True:
            shapeParentChildCout = om.MFnDagNode(om.MFnDagNode(omList.getDagPath(i)).parent(0)).childCount()
            if shapeParentChildCout >= 1:
                path = '|'.join(path.split('|')[:-1])

        shaders, indices = mesh.getConnectedShaders(0)
        prim = stage.OverridePrim(procPathNamespace(path))
        # prim = UsdGeom.Xform.Define(stage, procPathNamespace(path))

        root = stage.GetPrimAtPath('/').GetAllChildren()[0]
        scope = stage.OverridePrim(root.GetPath().AppendChild(scopeName))
        if len(shaders) == 1:
            shadingGroup_name = om.MFnDependencyNode(shaders[0]).name()
            usdMaterial = UsdShade.Material.Define(stage, scope.GetPrim().GetPath().AppendChild(
                procNamespace(shadingGroup_name)))
            if transformAssign is True and merge is False:
                UsdShade.MaterialBindingAPI(prim.GetParent()).Bind(usdMaterial, materialPurpose=materialPurpose)
            else:
                UsdShade.MaterialBindingAPI(prim).Bind(usdMaterial, materialPurpose=materialPurpose)

        elif len(shaders) > 1:
            shadingGroup_names = [om.MFnDependencyNode(x).name() for x in shaders]
            for shader_index, shadingGroup_name in zip(range(len(shadingGroup_names)), shadingGroup_names):
                geomSubset = UsdGeom.Subset.Define(stage, prim.GetPrim().GetPath().AppendChild(
                    procNamespace(shadingGroup_name)))
                geomSubset.CreateElementTypeAttr('face')
                geomSubset.CreateIndicesAttr([i for i, x in enumerate(indices) if x == shader_index])
                usdMaterial = UsdShade.Material.Define(stage, scope.GetPrim().GetPath().AppendChild(
                    procNamespace(shadingGroup_name)))
                UsdShade.MaterialBindingAPI(geomSubset).Bind(usdMaterial, materialPurpose=materialPurpose)

    # Setting default primitive
    rootPrim = stage.GetPrimAtPath('/').GetAllChildren()[0]
    if assetVersion:
        rootPrim.SetAssetInfoByKey('version', assetVersion)
    if assetName:
        rootPrim.SetAssetInfoByKey('name', assetName)
    stage.SetDefaultPrim(rootPrim)

    # Export tmp path
    outpath_tmp = os.path.join(os.path.dirname(out_path), 'assign_tmp.usda')
    stage.Export(outpath_tmp)

    # Add active
    stage = Usd.Stage.CreateInMemory()
    layer = stage.GetRootLayer()
    layer.Import(outpath_tmp)
    skip_type = ['GeomSubset', 'Material']

    for prim in stage.TraverseAll():
        if prim.GetTypeName() in skip_type:
            continue
        prim.SetActive(_checkActive(str(prim.GetPath())))

    # print(stage.GetRootLayer().ExportToString())
    stage.GetRootLayer().Export(out_path)

    if parent_node:
        cmds.parent(dagObject, parent_node)

    # Remove tmp usda
    os.remove(outpath_tmp)

    return True
