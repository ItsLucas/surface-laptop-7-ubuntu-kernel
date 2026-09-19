// SPDX-License-Identifier: GPL-2.0-only
/* Qualcomm X1E PLD firmware power telemetry, protocol revision under study. */
#include <linux/efi.h>
#include <linux/hwmon.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/suspend.h>
#include <linux/workqueue.h>
#include <asm/pgtable.h>

#include "qcom_pld_cache.h"
#include "qcom_pld_protocol.h"

#define PLD_POLL_MS		1000

static const char * const pld_labels[PLD_CHANNELS] = {
	"CPU_CLUSTER_0", "CPU_CLUSTER_1", "CPU_CLUSTER_2", "GPU",
	"PSU_USB", "USBC_TOTAL", "SYS",
};

struct pld_data {
	void __iomem *base;
	struct pld_io io;
	struct mutex lock;
	struct notifier_block pm_nb;
	struct delayed_work poll_work;
	struct qcom_pld_freshness freshness;
	struct pld_sample sample;
	u64 last_kick_ns;
	int cached_error;
	bool suspended;
	bool stopping;
};

static u32 pld_read_head(void *context)
{
	struct pld_data *data = context;

	return readl(data->base + PLD_HEAD);
}

static u16 pld_read_power(void *context, u32 offset)
{
	struct pld_data *data = context;

	return readw(data->base + offset);
}

/* A deferrable timer does not wake an idle CPU merely to refresh hwmon. */
static void pld_poll(struct work_struct *work)
{
	struct pld_data *data = container_of(to_delayed_work(work),
					   struct pld_data, poll_work);
	struct pld_sample sample;
	u64 now;
	int ret;

	mutex_lock(&data->lock);
	if (data->suspended || data->stopping)
		goto out;
	ret = pld_snapshot(&data->io, &sample);
	now = ktime_get_boottime_ns();
	if (ret) {
		memset(&data->freshness, 0, sizeof(data->freshness));
	} else {
		ret = qcom_pld_observe(&data->freshness, sample.head, now);
		if (ret == -EAGAIN)
			ret = -ENODATA;
	}
	if (!ret)
		data->sample = sample;
	data->cached_error = ret;
	queue_delayed_work(system_freezable_wq, &data->poll_work,
			   msecs_to_jiffies(PLD_POLL_MS));
out:
	mutex_unlock(&data->lock);
}

static umode_t pld_is_visible(const void *priv, enum hwmon_sensor_types type,
			     u32 attr, int channel)
{
	if (type == hwmon_chip && attr == hwmon_chip_update_interval)
		return 0444;
	if (type == hwmon_power && channel >= 0 && channel < PLD_CHANNELS &&
	    (attr == hwmon_power_average || attr == hwmon_power_average_interval ||
	     attr == hwmon_power_label))
		return 0444;
	return 0;
}

static int pld_read(struct device *dev, enum hwmon_sensor_types type,
		    u32 attr, int channel, long *val)
{
	struct pld_data *data = dev_get_drvdata(dev);
	u64 now;
	int ret;

	if (type == hwmon_chip && attr == hwmon_chip_update_interval) {
		*val = 1000;
		return 0;
	}
	if (type != hwmon_power ||
	    channel < 0 || channel >= PLD_CHANNELS)
		return -EOPNOTSUPP;
	if (attr == hwmon_power_average_interval) {
		*val = 1000;
		return 0;
	}
	if (attr != hwmon_power_average)
		return -EOPNOTSUPP;
	mutex_lock(&data->lock);
	now = ktime_get_boottime_ns();
	ret = qcom_pld_cached_status(&data->freshness, now, data->cached_error,
				     data->suspended);
	if (!ret)
		*val = pld_microwatts(data->sample.power[channel]);
	/* A reader is already awake: kick a deferred refresh, without waiting. */
	if (ret && !data->suspended && !data->stopping &&
	    now - data->last_kick_ns >= 100000000ULL) {
		data->last_kick_ns = now;
		mod_delayed_work(system_freezable_wq, &data->poll_work, 0);
	}
	mutex_unlock(&data->lock);
	return ret;
}

static int pld_read_string(struct device *dev, enum hwmon_sensor_types type,
			   u32 attr, int channel, const char **str)
{
	if (type != hwmon_power || attr != hwmon_power_label ||
	    channel < 0 || channel >= PLD_CHANNELS)
		return -EOPNOTSUPP;
	*str = pld_labels[channel];
	return 0;
}

static const struct hwmon_ops pld_hwmon_ops = {
	.is_visible = pld_is_visible,
	.read = pld_read,
	.read_string = pld_read_string,
};

#define PLD_POWER_FLAGS (HWMON_P_AVERAGE | HWMON_P_AVERAGE_INTERVAL | HWMON_P_LABEL)
static const struct hwmon_channel_info * const pld_hwmon_info[] = {
	HWMON_CHANNEL_INFO(chip, HWMON_C_UPDATE_INTERVAL),
	HWMON_CHANNEL_INFO(power, PLD_POWER_FLAGS, PLD_POWER_FLAGS,
			   PLD_POWER_FLAGS, PLD_POWER_FLAGS, PLD_POWER_FLAGS,
			   PLD_POWER_FLAGS, PLD_POWER_FLAGS),
	NULL,
};

static const struct hwmon_chip_info pld_chip = {
	.ops = &pld_hwmon_ops,
	.info = pld_hwmon_info,
};

static int pld_pm_notify(struct notifier_block *nb, unsigned long action, void *v)
{
	struct pld_data *data = container_of(nb, struct pld_data, pm_nb);
	bool prepare;

	switch (action) {
	case PM_SUSPEND_PREPARE:
	case PM_HIBERNATION_PREPARE:
	case PM_RESTORE_PREPARE:
	case PM_POST_SUSPEND:
	case PM_POST_HIBERNATION:
	case PM_POST_RESTORE:
		prepare = action == PM_SUSPEND_PREPARE ||
			  action == PM_HIBERNATION_PREPARE ||
			  action == PM_RESTORE_PREPARE;
		mutex_lock(&data->lock);
		data->suspended = prepare;
		memset(&data->freshness, 0, sizeof(data->freshness));
		data->cached_error = -ENODATA;
		if (!prepare && !data->stopping)
			queue_delayed_work(system_freezable_wq, &data->poll_work, 0);
		mutex_unlock(&data->lock);
		if (prepare)
			cancel_delayed_work_sync(&data->poll_work);
	}
	return NOTIFY_OK;
}

static void pld_unmap(void *base)
{
	iounmap((void __iomem *)base);
}

static void pld_stop(void *priv)
{
	struct pld_data *data = priv;

	unregister_pm_notifier(&data->pm_nb);
	mutex_lock(&data->lock);
	data->stopping = true;
	mutex_unlock(&data->lock);
	cancel_delayed_work_sync(&data->poll_work);
}

static int pld_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct resource *res;
	struct pld_data *data;
	struct device *hwmon;
	efi_memory_desc_t md;
	int ret;

	BUILD_BUG_ON(PLD_RECORDS + PLD_CAPACITY * PLD_RECORD_SIZE > PLD_SIZE);
	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res || resource_size(res) != PLD_SIZE)
		return -EINVAL;
	if (region_intersects(res->start, PLD_SIZE, IORESOURCE_SYSTEM_RAM,
			      IORES_DESC_NONE) != REGION_DISJOINT)
		return -EBUSY;
	ret = efi_mem_desc_lookup(res->start, &md);
	if (ret)
		return dev_err_probe(dev, ret, "EFI memory map unavailable\n");
	if (md.type != EFI_RESERVED_TYPE || md.phys_addr > res->start ||
	    md.num_pages > (U64_MAX - md.phys_addr) >> EFI_PAGE_SHIFT ||
	    md.phys_addr + (md.num_pages << EFI_PAGE_SHIFT) <= res->end)
		return dev_err_probe(dev, -ENODEV, "resource is not EFI reserved memory\n");
	data = devm_kzalloc(dev, sizeof(*data), GFP_KERNEL);
	if (!data)
		return -ENOMEM;
	mutex_init(&data->lock);
	INIT_DEFERRABLE_WORK(&data->poll_work, pld_poll);
	data->io = (struct pld_io){
		.context = data,
		.head = pld_read_head,
		.power = pld_read_power,
	};
	data->cached_error = -ENODATA;
	if (!devm_request_mem_region(dev, res->start, PLD_SIZE, dev_name(dev)))
		return -EBUSY;
	/* arm64 ioremap_prot() strips RO; preserve it via __ioremap_prot(). */
	data->base = __ioremap_prot(res->start, PLD_SIZE,
				    pgprot_noncached(PAGE_KERNEL_RO));
	if (!data->base)
		return -ENOMEM;
	ret = devm_add_action_or_reset(dev, pld_unmap, (void __force *)data->base);
	if (ret)
		return ret;
	data->pm_nb.notifier_call = pld_pm_notify;
	ret = register_pm_notifier(&data->pm_nb);
	if (ret)
		return ret;
	ret = devm_add_action_or_reset(dev, pld_stop, data);
	if (ret)
		return ret;
	platform_set_drvdata(pdev, data);
	hwmon = devm_hwmon_device_register_with_info(dev, "qcom_pld_power", data,
							   &pld_chip, NULL);
	if (IS_ERR(hwmon))
		return PTR_ERR(hwmon);
	mutex_lock(&data->lock);
	if (!data->suspended)
		queue_delayed_work(system_freezable_wq, &data->poll_work, 0);
	mutex_unlock(&data->lock);
	return 0;
}

static const struct of_device_id pld_of_match[] = {
	{ .compatible = "qcom,x1e80100-pld-power" },
	{ }
};
MODULE_DEVICE_TABLE(of, pld_of_match);

static struct platform_driver pld_driver = {
	.probe = pld_probe,
	.driver = {
		.name = "qcom-pld-power",
		.of_match_table = pld_of_match,
	},
};
module_platform_driver(pld_driver);

MODULE_ALIAS("platform:qcom-pld-power");
MODULE_DESCRIPTION("Qualcomm X1E read-only PLD firmware power telemetry");
MODULE_LICENSE("GPL");
MODULE_VERSION("0.1.0");
