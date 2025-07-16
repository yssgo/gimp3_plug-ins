#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Sample plug-in used as reference/template:
#   test-file-plug-ins.py 2021-2024 Jacob Boerema
#
# Compatability:
#   Tested and working on:
#
#     version: 3.0.0-RC1+git
#     Installation method: Flatpak
#     Flatpak output:
#       GNU Image Manipulation Program  org.gimp.GIMP   3.0.0~rc1       master    gnome-nightly   system
#
#
# Script path:
#   ~/.config/GIMP/3.0/plug-ins/group_selected_layers/group_selected_layers.py

# Comment by yssgo
# ================
# Compatability:
#   Tested and working on:
#     GIMP version: 3.0.4
#     Platform : Windows 11
# Script path:
#   %APPDATA%/GIMP/3.0/plug-ins/group_selected_layers/group_selected_layers.py

import sys

import gi


def N_(message): return message
def _(message): return GLib.dgettext(None, message)

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp

gi.require_version("GimpUi", "3.0")
from gi.repository import GimpUi

from gi.repository import GLib
from gi.repository import GObject

VERSION = "0.44.3"
AUTHORS = "newinput"
COPYRIGHT = "newinput"
YEARS = "2023-2024"


def N_(message):
    return message


def _(message):
    return GLib.dgettext(None, message)


class GroupSelectedLayers(Gimp.PlugIn):

    # def __init__(self):
    # super().__init__()
    # self.test_cfg = None
    # self.log = None

    # === GimpPlugIn virtual methods ===

    # I would remove this part but I get these messages in the console whenever it's commented out:
    # -------------------------------------
    # [group-selected-layers] The catalog directory does not exist: /home/newinput/.var/app/org.gimp.GIMP/config/GIMP/3.0/plug-ins/group_selected_layers/locale
    # [group-selected-layers] Override method set_i18n() for the plug-in to customize or disable localization.
    # [group-selected-layers] Localization disabled
    # -------------------------------------
    # Not sure if it's better to let it complain and then disable it itself
    #
    # Gimp 3.0.4 does not need this. -- yssgo
    # def do_set_i18n(self, _name):
    #    # We don't support internationalization here...
    #    return False

    def do_query_procedures(self):
        return ["group-selected-layers"]

    def do_create_procedure(self, name):

        if name == "group-selected-layers":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.group_selected_layers, None
            )
            procedure.set_image_types("*")

            # Allow user to also create group from one selected layer for more flexible workflow
            #
            # eg. If you want to add a screen layer that only affects the single
            #     currently selected layer, it would be better if you could nest it first
            #     before doing that so it only applies to that single layer from the get-go.
            #
            procedure.set_sensitivity_mask(
                Gimp.ProcedureSensitivityMask.DRAWABLES
                | Gimp.ProcedureSensitivityMask.DRAWABLE
            )

            procedure.add_string_argument(
                "group_name",
                _("Group name:"),
                _("The layer name of the new group layer."),
                _("Layer Group"),
                GObject.ParamFlags.READWRITE,
            )

            procedure.set_menu_label(_("Group Selected Layers"))
            procedure.add_menu_path(N_("<Image>/Filters/Development/Python-Fu/"))
            procedure.add_menu_path(N_("<Image>/Layer/Stack/"))

            # I'm not sure why there is a single /Layers Menu section when you right click a layer right now
            # though if I don't nest it in there it looks like this:
            #
            #  -----------------------
            # | Layers Menu >         |
            # | Group Selected Layers |
            # |                       |
            # |                       |
            #  -----------------------
            #
            procedure.add_menu_path(N_("<Layers>/Layers Menu"))

            # Only part that is ChatGpt written since I take way to long wording things.
            # It's good I think. Much better than what I had before at least...
            #
            procedure.set_documentation(
                _("Group Selected Layers"),
                _(
                    "Creates a new layer group and moves all selected layers into it, maintaining their stacking order."
                ),
                name,
            )

        else:
            return None

        procedure.set_attribution(AUTHORS, COPYRIGHT, YEARS)
        return procedure

    def group_selected_layers(
        self, procedure, run_mode, image, n_drawables, config, run_data
    ):
        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init(procedure.get_name())

            dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config)

            dialog.fill(
                [
                    "TEXT",
                    "group_name",
                ]
            )

            if not dialog.run():
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )
            group_name = config.get_property("group_name")
            if not group_name:
                group_name = None
        else:
            group_name = None

        # using undo_group so undo doesn't need to return each item one at a time and then remove the group...
        image.undo_group_start()

        # => record currently selected layers
        #
        #    (is needed since inserting a new layer replaces the current selection with just the newly inserted layer)
        #
        selected_layers = []
        for drawable in n_drawables:
            if drawable not in selected_layers and (
                Gimp.Item.is_layer(drawable) or Gimp.Item.is_group_layer(drawable)
            ):
                selected_layers.append(drawable)

        # => if the selected drawable is a mask then
        #    find and get all selected layers
        #
        #    (
        #      Need to do the search here since there's currently not any kind
        #      of layer_mask.get_layer() function that would allow us to simply
        #      use the passed in drawable to get the layer.
        #    )
        #
        # This block is especially ugly I know :{
        #
        # Adding this in though so the user doesn't have to think about
        # whether edit_mask is toggled when trying to group the layer
        #
        # if found no selected Layer/GroupLayer types
        if len(selected_layers) == 0:

            # (masks don't work with multi-selection currently)
            # Not sure if should account for the possibility of multi-selection working with masks? Probably won't be added?
            #
            if len(n_drawables) == 1 and Gimp.Item.is_layer_mask(n_drawables[0]):
                # selected_layers = [layer for layer in image.get_selected_layers() if layer.get_mask() === n_drawables[0]] # ...not necessary?
                selected_layers = (
                    image.get_selected_layers()
                )  # or singular 'layer' rather

        # => get all unique parent layers
        parents = []

        layers_to_move = selected_layers
        for layer in selected_layers:

            parent = layer.get_parent()

            # if a layer's parent is also selected, keep the parent, omit the layer (child).
            #
            if parent in selected_layers:
                # remove child
                layers_to_move = [s for s in layers_to_move if s is not layer]

            # using elif here so we only add parent if it is NOT also selected
            # removes the possibility of trying to nest a selected parent inside itself
            #
            elif parent not in parents:
                parents.append(parent)

        # At this point, len(parents) will equal zero (0)
        # if n_drawables did not contain any of the following types:
        #   - layer
        #   - layer_group
        #   - layer_mask
        #
        # This can happen with non-layer_mask channels like quickmask
        # or channels in the channels panel.
        #
        if len(parents) == 0:
            Gimp.message(
                "\n".join(
                    [
                        _("Error: Expected drawable types:"),
                        "    "
                        + "\n    ".join(
                            [str(Gimp.Layer), str(Gimp.GroupLayer), str(Gimp.LayerMask)]
                        ),
                        _("Instead got drawable types:"),
                        "    "
                        + "\n    ".join(
                            str(type(drawable)) for drawable in n_drawables
                        ),
                        _(
                            """\
-----------------------
Please make sure you have at least one Layer or Group Layer selected.
-----------------------
Hint:
Will not work if Quick Mask is currently active,
or another selection mask eg. one created via 'Save To Channel' is currently selected.

You can check the status bar to confirm what you currently have selected"""
                        ),
                    ]
                )
            )
        else:

            # => create new group
            # if name is None(default), localized Group layer name will be used. -- commenter: yssgo
            new_group = Gimp.GroupLayer.new(
                image, name=group_name
            )  # (image, "Layer Group")

            # if the layers are under same parent
            if len(parents) == 1:
                new_group_parent = parents[
                    0
                ]  # insert the new group layer inside that parent
                topmost_position = min(
                    [image.get_item_position(layer) for layer in layers_to_move]
                )

            # if the layers not under same parent
            elif len(parents) > 1:
                new_group_parent = (
                    None  # insert group layer in the main stack, unnested
                )
                topmost_position = 0

            # => insert new group into image
            image.insert_layer(
                new_group,  # group to insert
                new_group_parent,  # parent nest group inside of. None = unnested
                topmost_position,  # index/stack-postition within parent (0 = insert as topmost layer within parent)
            )

            for layer in layers_to_move:
                image.reorder_item(
                    layer,  # layer to reorder
                    new_group,  # parent to nest inside
                    1,  # index/stack-postition within parent
                )

        image.undo_group_end()

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


Gimp.main(GroupSelectedLayers.__gtype__, sys.argv)
