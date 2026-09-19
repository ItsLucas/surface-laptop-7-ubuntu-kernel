// SPDX-License-Identifier: GPL-2.0-only
/* Local bridge for an observed firmware resource absent from the stock DT. */
#include <linux/dmi.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct platform_device *pld_device;

static const struct dmi_system_id sl7_pld_dmi[] = {
	{
		.matches = {
			DMI_EXACT_MATCH(DMI_SYS_VENDOR, "Microsoft Corporation"),
			DMI_EXACT_MATCH(DMI_PRODUCT_NAME,
					"Microsoft Surface Laptop, 7th Edition"),
			DMI_EXACT_MATCH(DMI_BIOS_VERSION, "175.235.235"),
		},
	},
	{ }
};
MODULE_DEVICE_TABLE(dmi, sl7_pld_dmi);

static const struct resource pld_resources[] = {
	DEFINE_RES_MEM(0x81f30000, 0x6000),
};

static int __init sl7_pld_init(void)
{
	struct device_node *np;

	if (!of_machine_is_compatible("microsoft,romulus13") ||
	    !of_machine_is_compatible("qcom,x1e80100") ||
	    !dmi_check_system(sl7_pld_dmi))
		return -ENODEV;
	np = of_find_compatible_node(NULL, NULL, "qcom,x1e80100-pld-power");
	if (np) {
		of_node_put(np);
		return -EEXIST;
	}
	pld_device = platform_device_register_simple("qcom-pld-power",
						     PLATFORM_DEVID_NONE,
						     pld_resources,
						     ARRAY_SIZE(pld_resources));
	return PTR_ERR_OR_ZERO(pld_device);
}

static void __exit sl7_pld_exit(void)
{
	platform_device_unregister(pld_device);
}

module_init(sl7_pld_init);
module_exit(sl7_pld_exit);
MODULE_SOFTDEP("pre: qcom_pld_power");
MODULE_DESCRIPTION("Romulus13 BIOS 175.235.235 PLD device bridge");
MODULE_LICENSE("GPL");
MODULE_VERSION("0.1.0");
