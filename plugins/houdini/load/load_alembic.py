from avalon import api, io

from avalon.houdini import pipeline
from reveries.houdini.plugins import HoudiniBaseLoader
from reveries.utils import get_representation_path_


class AbcLoader(HoudiniBaseLoader, api.Loader):
    """Specific loader of Alembic for the avalon.animation family"""

    families = ["reveries.model",
                "reveries.pointcache"]
    label = "Load Alembic"
    representations = ["Alembic"]
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        import hou

        # Format file name, Houdini only wants forward slashes
        representation = context["representation"]
        file_path = self.file_path(representation)
        file_path = file_path.replace("\\", "/")
        if file_path.endswith(".ma"):
            file_path = file_path.rsplit("ma", 1)[0] + "abc"

        # Get the root node
        obj = hou.node("/obj")

        # Define node name
        namespace = namespace if namespace else context["asset"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        # Create a new geo node
        container = obj.createNode("geo", node_name=node_name)

        # Remove the file node, it only loads static meshes
        # Houdini 17 has removed the file node from the geo node
        file_node = container.node("file1")
        if file_node:
            file_node.destroy()

        # Create an alembic node (supports animation)
        alembic = container.createNode("alembic", node_name=node_name)
        alembic.setParms({"fileName": file_path,
                          # Enable "Add Filename Attribute" to read AvalonID
                          "addfile": True})

        null = container.createNode("null", node_name="OUT".format(name))
        null.setInput(0, alembic)

        # Set display on last node
        null.setDisplayFlag(True)

        # Set new position for unpack node else it gets cluttered
        nodes = [container, alembic, null]
        for nr, node in enumerate(nodes):
            node.setPosition([0, (0 - nr)])

        self[:] = nodes

        return pipeline.containerise(node_name,
                                     namespace,
                                     nodes,
                                     context,
                                     self.__class__.__name__,
                                     suffix="")

    def update(self, container, representation):

        node = container["node"]
        try:
            alembic_node = next(n for n in node.children() if
                                n.type().name() == "alembic")
        except StopIteration:
            self.log.error("Could not find node of type `alembic`")
            return

        # Update the file path
        parents = io.parenthood(representation)
        self.package_path = get_representation_path_(representation, parents)
        file_path = self.file_path(representation)
        file_path = file_path.replace("\\", "/")
        if file_path.endswith(".ma"):
            file_path = file_path.rsplit("ma", 1)[0] + "abc"

        alembic_node.setParms({"fileName": file_path})

        # Update attribute
        node.setParms({"representation": str(representation["_id"])})

    def remove(self, container):

        node = container["node"]
        node.destroy()

    def switch(self, container, representation):
        self.update(container, representation)
