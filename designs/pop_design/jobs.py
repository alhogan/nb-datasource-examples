"""Initial data required for core sites."""

from nautobot_design_builder.design_job import DesignJob

from nautobot.dcim.models import Device, VirtualChassis
from nautobot.extras.jobs import StringVar, BooleanVar

from .context import (
    BranchContext,
    BaseContext,
)


# Stage 1
class CreateBase(DesignJob):
    """Job to create base elements."""

    class Meta:
        """Meta class for CreateBase."""

        name = "Branch: Stage #1 - Deploy branch base elements"
        commit_default = True
        description = "Use this form to create base for branch in clean Nautobot"
        design_file = "designs/0001_base.yaml.j2"
        context_class = BaseContext
        # report = "design_files/templates/backbone/pops_report.md.j2"
        has_sensitive_variables = False

    def post_implementation(self, context, creator):
        # TODO: This is done since the filter does not work on dynamic group.
        # Once https://github.com/nautobot/nautobot-app-design-builder/pull/218 is addressed, this can be removed.
        from nautobot.extras.models.groups import DynamicGroup

        for group_name in [
            "AMER Branch Access",
            "EMEA Branch Access",
            "APAC Branch Access",
        ]:
            region = group_name.split(" ")[0]
            dg = DynamicGroup.objects.get(name=group_name)
            dg.filter = {"location": [region], "role": ["branch_access"]}
            dg.validated_save()
            dg.update_cached_members()


# Stage 2
class CreateBranch(DesignJob):
    """Job to create a new site of type Branch."""

    site_name = StringVar(
        description="Site Name",
        label="Site Name",
    )
    region_name = StringVar(
        description="Region of the new site",
        label="Region Name",
    )
    country_name = StringVar(
        description="Country of the new site",
        label="Country Name",
        default="United States of America",
    )
    site_facility = StringVar(
        description="Facility of the new site",
        label="Facility Name",
    )
    status = StringVar(
        description="Status the new site",
        label="Site Status",
        default="Planned",
    )
    site_latitude = StringVar(
        description="Site latitude",
        label="Site latitude",
        default="50.000000",
    )
    site_longitude = StringVar(
        description="Longitude",
        label="Longitude",
        default="50.000000",
    )
    physical_address = StringVar(
        description="Physical Address",
        label="Physical Address",
        default="100 Network Drive, Somewhere, TX 70000",
    )
    has_experimental_sdwan_deployment = BooleanVar(
        description="Experimental SDWAN",
        label="Experimental SDWAN",
    )

    class Meta:
        """Meta class for CreateBranch."""

        name = "Branch: Stage #2 - Deploy branch"
        commit_default = True
        description = "Use this form to create branch in clean Nautobot"
        design_file = "designs/0002_branch.yaml.j2"
        context_class = BranchContext
        # report = "design_files/templates/backbone/pops_report.md.j2"
        has_sensitive_variables = False

    def post_implementation(self, context, creator):
        # Update BGP Peerings for remote peer information.
        try:
            from nautobot_bgp_models.models import Peering

            for peering in Peering.objects.all():
                peering.validate_peers()
                peering.update_peers()
        except:
            pass
        # TDOO: See `virtual_chassis:` in 200_branch.yaml.j2 for details.
        chassis_name = f"{context.site_name.lower()}-dsw-01"
        virtual_chassis = VirtualChassis.objects.get(name=chassis_name)
        virtual_chassis.master = Device.objects.get(name=chassis_name)
        virtual_chassis.save()
