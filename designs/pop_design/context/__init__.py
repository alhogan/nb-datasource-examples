from functools import cached_property

from django.conf import settings
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

from nautobot_design_builder.context import Context, context_file
from nautobot_design_builder.jinja_filters import network_string, network_offset
from nautobot.ipam.models import Prefix
from nautobot.dcim.models import Device, Interface, Location, LocationType
from ..helpers.ipam import (
    get_global_available_ipset,
    get_ipnetwork_of_prefixlen_from_ipset,
)

import netaddr


def site_code_to_number(site_code):
    # Extract the prefix (everything except the last number)
    site_code_len = len(site_code) - 1
    while site_code_len >= 0 and site_code[site_code_len].isdigit():
        site_code_len -= 1
    site_chars = site_code[: site_code_len + 1]
    last_number = site_code[site_code_len + 1 :]

    # Convert the last number to an integer
    try:
        last_number_int = int(last_number)
    except ValueError:
        # If there's no numeric suffix, use 0
        last_number_int = 0

    # Create a deterministic hash based on the site_chars
    # This ensures different site_charses can have overlapping numbers
    site_chars_hash = sum(ord(char) for char in site_chars) % 10

    # Combine the site_chars hash and last number to get the final number
    # We use (site_chars_hash + last_number_int) % 10 to ensure outputs are between 0-9
    output_number = (site_chars_hash + last_number_int) % 10

    return output_number


@context_file("branch_context.yml")
class BaseContext(Context):
    @property
    def INSTALLED_PLUGINS(self):
        return {plugin: apps.get_app_config(plugin) for plugin in settings.PLUGINS}


@context_file("branch_context.yml", "device_profiles.yaml")
class BranchContext(Context):
    @cached_property
    def branch_prefix(self):
        def get_global_available_ipset():
            """
            Compose IPSet of all Prefixes with role's name of `global_branch_container_role_name`.
            """
            containers = Prefix.objects.filter(
                role__name=self.global_branch_container_role_name
            )

            available_ipset = netaddr.IPSet()

            for _container in containers:
                available_ipset = available_ipset | _container.get_available_prefixes()

            return available_ipset

        def get_ipnetwork_of_prefixlen_from_ipset(ipset, prefixlen):
            for ipset_prefix in ipset.iter_cidrs():
                if prefixlen >= ipset_prefix.prefixlen:
                    ipnetwork = netaddr.IPNetwork(
                        "{}/{}".format(ipset_prefix.network, prefixlen)
                    )
                    return ipnetwork
            raise ValueError("Could not find available IPNetwork within IPSet")

        try:
            _branch_prefix = Prefix.objects.get(
                role__name=self.branch_container_role_name,
                locations__in=[Location.objects.get(name=self.site_name).pk],
            ).prefix
        except ObjectDoesNotExist:
            available_ipset = get_global_available_ipset()
            _branch_prefix = get_ipnetwork_of_prefixlen_from_ipset(
                available_ipset, self.branch_prefixlen
            )

        return _branch_prefix

    @property
    def INSTALLED_PLUGINS(self):
        return {plugin: apps.get_app_config(plugin) for plugin in settings.PLUGINS}


@context_file("branch_context.yml", "device_profiles.yaml")
class BranchAccessSwitchContext(Context):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        vlan_10s = site_code_to_number(self.location.name)
        count = Device.objects.filter(
            location__name__istartswith=self.location.name,  # TODO(mzb): Ask Glenn how to filter devices in nested locations
            role__name=self.branch_access_role,
        ).count()
        desired_location_type = LocationType.objects.get(
            name="Region"
        )  # or whatever you need
        region = (
            self.location.ancestors()
            .filter(location_type=desired_location_type)
            .first()
            .name
        )

        self._data_vlan_id = f"{self.data_vlan_hundred[region]}{vlan_10s}{count + 1}"
        self._voice_vlan_id = f"{self.voice_vlan_hundred[region]}{vlan_10s}{count + 1}"

        # Static allocation for 2x /24.
        aggregated_prefixlen = 23

        # Get branch specific IPSet
        branch_ipset = get_global_available_ipset(
            nb_prefixes=Prefix.objects.filter(
                id=self.branch_prefix.id
            )  # branch prefixes
        )

        # Find IPNetwork of an `aggregated_prefixlen` size, inside the branch specific prefix
        self._asw_prefix = get_ipnetwork_of_prefixlen_from_ipset(
            ipset=branch_ipset,
            prefixlen=aggregated_prefixlen,
        )

    @property
    def switch_region(self):
        return self.location.parent.parent.name

    @property
    def site_name(self):
        return self.location.name

    @cached_property
    def branch_access_switch_hostname(self):
        count = Device.objects.filter(
            location__name__istartswith=self.location.name,  # TODO(mzb): Ask Glenn how to filter devices in nested locations
            role__name=self.branch_access_role,
        ).count()

        host_id = str(count + 1).zfill(2)

        return f"{self.location.name}-asw-{host_id}".lower()

    @cached_property
    def branch_distribution_switch(self):
        return Device.objects.get(
            location__name__istartswith=self.location.name,  # TODO(mzb): Ask Glenn how to filter devices in nested locations
            role__name=self.branch_distribution_role,
            status__name="Active",  # TODO(mzb): deterministic
        )

    @cached_property
    def branch_prefix(self):
        branch_prefix = Prefix.objects.get(
            role__name=self.branch_container_role_name,
            locations__in=[self.location.pk],
        )

        return branch_prefix

    @cached_property
    def data_prefix(self):
        return network_offset(
            prefix=network_string(self._asw_prefix),
            offset="0.0.0.0/24",
        )

    @cached_property
    def voice_prefix(self):
        return network_offset(
            prefix=network_string(self._asw_prefix),
            offset="0.0.1.0/24",
        )

    @property
    def data_vlan_id(self):
        return self._data_vlan_id

    @property
    def voice_vlan_id(self):
        return self._voice_vlan_id

    @cached_property
    def uplink_a_dsw(self):
        return Interface.objects.filter(
            device__name=self.branch_distribution_switch,
            cable__isnull=True,
            tags__name="access_switch_a_allocation",
        ).first()

    @cached_property
    def uplink_b_dsw(self):
        return Interface.objects.filter(
            device__name=self.branch_distribution_switch,
            cable__isnull=True,
            tags__name="access_switch_b_allocation",
        ).first()
