import netaddr

offsets = {
    32: "0.0.0.1",
    31: "0.0.0.2",
    30: "0.0.0.4",
    29: "0.0.0.8",
    28: "0.0.0.16",
    27: "0.0.0.32",
    26: "0.0.0.64",
    25: "0.0.0.128",
    24: "0.0.1.0",
    23: "0.0.2.0",
    22: "0.0.4.0",
    21: "0.0.8.0",
    20: "0.0.16.0",
    19: "0.0.32.0",
    18: "0.0.64.0",
    17: "0.0.128.0",
    16: "0.1.0.0",
}


def get_aggregated_prefixlen(*prefixlens):
    """
    Get an "aggregated" (minimum) prefixlen spanning over prefix lengths provided.

    Example (with extra slashes for brevity):
        prefixlen_1 (net1): /24
        prefixlen_2 (net2): /24

        result: /23

    Args: prefix lengths (ints)

    Returns: int
    """
    max_prefixlen = 32  # TODO(mzb): Add IPv6 Support (current is IPv4 only)

    if not all(x <= max_prefixlen for x in prefixlens):
        raise ValueError("Invalid prefix length specified as an argument")

    addresses_sum = sum([2 ** (max_prefixlen - x) for x in prefixlens])

    aggregated_prefixlen = None

    for i in range(max_prefixlen, -1, -1):
        if 2 ** (max_prefixlen - i) >= addresses_sum:
            aggregated_prefixlen = i
            break

    if not aggregated_prefixlen:
        raise ValueError("Can not find an aggregated prefixlen")

    return aggregated_prefixlen


def get_global_available_ipset(nb_prefixes):
    """
    Compose IPSet of all Prefixes with role's slug of `global_branch_container_role_name`.
    """
    containers = nb_prefixes

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
