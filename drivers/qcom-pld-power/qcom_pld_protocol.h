/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef QCOM_PLD_PROTOCOL_H
#define QCOM_PLD_PROTOCOL_H

#include <linux/errno.h>
#include <linux/string.h>
#include <linux/types.h>

#define PLD_SIZE			0x6000
#define PLD_HEAD			0x2938
#define PLD_RECORDS		0x2940
#define PLD_CAPACITY		128
#define PLD_RECORD_SIZE		40
#define PLD_CHANNELS		7

struct pld_sample {
	u32 head;
	u16 power[PLD_CHANNELS];
};

/* The transport permits testing torn publications without touching hardware. */
struct pld_io {
	void *context;
	u32 (*head)(void *context);
	u16 (*power)(void *context, u32 offset);
};

static inline int pld_snapshot(const struct pld_io *io, struct pld_sample *sample)
{
	static const u32 offsets[PLD_CHANNELS] = { 8, 10, 12, 14, 26, 28, 24 };
	u16 second[PLD_CHANNELS];
	u32 middle, after, offset;
	unsigned int attempt, ch;

	for (attempt = 0; attempt < 4; attempt++) {
		sample->head = io->head(io->context);
		offset = PLD_RECORDS + ((sample->head - 1) % PLD_CAPACITY) *
			 PLD_RECORD_SIZE;
		for (ch = 0; ch < PLD_CHANNELS; ch++)
			sample->power[ch] = io->power(io->context, offset + offsets[ch]);
		middle = io->head(io->context);
		for (ch = 0; ch < PLD_CHANNELS; ch++)
			second[ch] = io->power(io->context, offset + offsets[ch]);
		after = io->head(io->context);
		if (sample->head != middle || middle != after ||
		    memcmp(sample->power, second, sizeof(second)))
			continue;
		for (ch = 0; ch < PLD_CHANNELS; ch++)
			if (sample->power[ch] == 0xffffU)
				return -ENODATA;
		return 0;
	}
	return -EIO;
}

static inline u32 pld_microwatts(u16 raw)
{
	return (u32)raw * 10000U;
}

#endif
