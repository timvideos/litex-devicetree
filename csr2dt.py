#!/usr/bin/env python3

"""
Small Python module which generates Linux device tree from the csr.csv file
created by LiteX in the HDMI2USB-litex-firmware repo.

"""

import sys
import csv

import argparse

parser = argparse.ArgumentParser(description="LiteX SoC CSR CSV file to Device Tree Generator")
parser.add_argument("--csr_csv", action="store", default=None)

from collections import namedtuple

MemoryRegion = namedtuple("MemoryRegion", ["name", "start", "size"])
CSR = namedtuple("CSR", ["name", "location", "width", "mode"])

templates = {}

templates["or1k"] = lambda d: """
/dts-v1/;
/ {
	compatible = "opencores,or1ksim";
	#address-cells = <1>;
	#size-cells = <1>;
	interrupt-parent = <&pic>;

%(memories)s

	cpus {
		#address-cells = <1>;
		#size-cells = <0>;
		cpu@0 {
			compatible = "opencores,or1200-rtlsvn481";
			reg = <0>;
			clock-frequency = <%(config_clock_frequency)s>;
		};
	};

	pic: pic {
		compatible = "opencores,or1k-pic";
		#interrupt-cells = <1>;
		interrupt-controller;
	};

%(devices)s
};
""" % d

templates["lm32"] = lambda d: """
/dts-v1/;
/ {
	compatible = "opencores,or1ksim";
	#address-cells = <1>;
	#size-cells = <1>;
	interrupt-parent = <&pic>;

	aliases {
		uart0 = &serial0;
	};

	chosen {
		bootargs = "earlycon console=ttyLX0,115200";
		stdout-path = "uart0:115200";
	};

	cpus {
		#address-cells = <1>;
		#size-cells = <0>;
		cpu@0 {
			compatible = "opencores,or1200-rtlsvn481";
			reg = <0>;
			clock-frequency = <%(config_clock_frequency)s>;
		};
	};

	pic: pic {
		compatible = "opencores,or1k-pic";
		#interrupt-cells = <1>;
		interrupt-controller;
	};
};
""" % d

templates["uart"] = lambda m: """
	aliases {
		uart0 = &serial0;
	};

	chosen {
		bootargs = "earlycon console=ttyLX0,%(uart_baud)s";
		stdout-path = "uart0:%(uart_baud)s";
	};

	serial0: serial@%(location)x {
		device_type = "serial";
		compatible = "litex,litex-uart";
		reg = <0x%(location)x 0x100>;
		interrupts = <%(interrupt)i>;
	};
""" % {
    'uart_baud': m.constants.get('baud', 115200),
    'location': m.location,
    'size': m.size,
    'interrupt': m.interrupt or -1,
}

templates["ps2"] = """
ps2@0 {
	compatible = "ps2-gpio";
	interrupt-parent = <&gpio>;
	interrupts = <23 IRQ_TYPE_EDGE_FALLING>;
	data-gpios = <&gpio 24 GPIO_ACTIVE_HIGH>;
	clk-gpios = <&gpio 23 GPIO_ACTIVE_HIGH>;
	write-enable;
};
"""

templates["spi"] = """
	spi {
		compatible = "spi-gpio";
		#address-cells = <0x1>;
		ranges;

		gpio-sck = <&gpio 95 0>;
		gpio-miso = <&gpio 98 0>;
		gpio-mosi = <&gpio 97 0>;
		cs-gpios = <&gpio 125 0>;
		num-chipselects = <1>;

		/* clients */
	};

/*
cs0 : &gpio1 0 0
cs1 : native
cs2 : &gpio1 1 0
cs3 : &gpio1 2 0
*/

"""

templates["memory-ethmac"] = lambda m: """
	ethmac-sram: sram@%(start)x {
		compatible = "mmio-sram";
		reg = <0x%(start)x 0x%(size)x>;

		#address-cells = <1>;
		#size-cells = <1>;
		ranges = <0 0x%(start)x 0x%(size)x>;

		ethmac-pool@0 {
			reg = <0 0x%(size)x>;
			pool;
		};
	};
""" % {'start': m.start, 'size': m.size}

templates["memory-sram"] = lambda m: """
	sram: sram@%(start)x {
		compatible = "mmio-sram";
		reg = <0x%(start)x 0x%(size)x>;

		#address-cells = <1>;
		#size-cells = <1>;
		ranges = <0 0x%(start)x 0x%(size)x>;

		sram-pool@0 {
			reg = <0 0x%(size)x>;
			pool;
		};
	};
""" % {'start': m.start, 'size': m.size}


templates["ac97"] = """
ssi {
	...

	pinctrl-names = "default", "ac97-running", "ac97-reset", "ac97-warm-reset";
	pinctrl-0 = <&ac97link_running>;
	pinctrl-1 = <&ac97link_running>;
	pinctrl-2 = <&ac97link_reset>;
	pinctrl-3 = <&ac97link_warm_reset>;
	ac97-gpios = <&gpio3 20 0 &gpio3 22 0 &gpio3 28 0>;

	...
};
"""

templates["memory-main_ram"] = lambda m: """
	memory@0 {
		device_type = "memory";
		reg = <0x%(start)x 0x%(size)x>;
	};
""" % {'start': m.start, 'size': m.size}

# Extra memory stuff
"""

/ {
	#address-cells = <1>;
	#size-cells = <1>;

	memory {
		reg = <0x40000000 0x40000000>;
	};

	reserved-memory {
		#address-cells = <1>;
		#size-cells = <1>;
		ranges;

		/* global autoconfigured region for contiguous allocations */
		linux,cma {
			compatible = "shared-dma-pool";
			reusable;
			size = <0x4000000>;
			alignment = <0x2000>;
			linux,cma-default;
		};

		display_reserved: framebuffer@78000000 {
			reg = <0x78000000 0x800000>;
		};

		multimedia_reserved: multimedia@77000000 {
			compatible = "acme,multimedia-memory";
			reg = <0x77000000 0x4000000>;
		};
	};

	/* ... */

	fb0: video@12300000 {
		memory-region = <&display_reserved>;
		/* ... */
	};

	scaler: scaler@12500000 {
		memory-region = <&multimedia_reserved>;
		/* ... */
	};

	codec: codec@12600000 {
		memory-region = <&multimedia_reserved>;
		/* ... */
	};
};


"""

templates["spiflash"] = lambda m: """
	flash: m25p80@0 {
		#address-cells = <1>;
		#size-cells = <1>;
		compatible = "spansion,m25p80", "jedec,spi-nor";
		reg = <0>;
		spi-max-frequency = <40000000>;
		m25p,fast-read;
	};

	/* SPI Flash controller
	 ************************************************************************/
	spiflash: spiflash@20000000 {
		compatible = "mtd-rom";
		reg = <0x20000000 0x00200000>;
		bank-width = <4>;
		#address-cells = <1>;
		#size-cells = <1>;

		// Values in the partition table should be relative to the
		// flash start address...
		partitions {
			compatible = "fixed-partitions";
			#address-cells = <1>;
			#size-cells = <1>;

			/* FPGA gateware */
			partition@0 {
				label = "gateware";
				reg = <0x0000000 0x80000>;
				read-only;
			};

			/* MiSoC / LiteX BIOS */
			partition@80000 {
				label = "bios";
				reg = <0x00080000 0x8000>;
				read-only;
			};

			/* HDMI2USB Firmware (or Linux Kernel?) */
			partition@88000 {
				label = "firmware";
				reg = <0x00088000 0x178000>;
				read-only;
			};
		};
	};

	spiflash_bitbang_out: gpio-controller@e0005000 {
		compatible = "basic-mmio-gpio", "wd,mbl-gpio";
		reg = <0xe0005000 0x4>;
		#gpio-cells = <2>;
		ngpios = <3>;
		gpio-line-names = "SPI MOSI", "SPI SCLK", "SPI CS_N";
		gpio-controller;
		reg-names = "dat";
		big-endian;
	};
	spiflash_bitbang_in: gpio-controller@e0005004 {
		compatible = "basic-mmio-gpio", "wd,mbl-gpio";
		reg = <0xe0005004 0x4>;
		#gpio-cells = <2>;
		ngpios = <1>;
		gpio-line-names = "SPI MISO";
		gpio-controller;
		reg-names = "dat";
		no-output;
		big-endian;
	};
	spiflash_bitbang_en: gpio-controller@e0005008 {
		compatible = "basic-mmio-gpio", "wd,mbl-gpio";
		reg = <0xe0005008 0x4>;
		#gpio-cells = <2>;
		ngpios = <1>;
		gpio-line-names = "SPI BitBang EN";
		gpio-controller;
		reg-names = "dat";
		big-endian;

		spi_bitbang_en {
			gpio-hog;
			gpios = <0 0>;
			output-high;
		};
	};

        spi {
                compatible = "spi-gpio";
                #address-cells = <0x1>;
                ranges;

                gpio-mosi =	<&spiflash_bitbang_out 0 0>;	// 0x01 on reg0
                gpio-sck =	<&spiflash_bitbang_out 1 0>;	// 0x02 on reg0
                cs-gpios = 	<&spiflash_bitbang_out 2 0>;	// 0x03 on reg0
                gpio-miso = 	<&spiflash_bitbang_in  0 0>;	// 0x01 on reg1
                num-chipselects = <1>;

                /* clients */
		m25p16@0 {
			#address-cells = <1>;
			#size-cells = <1>;
			compatible = "spansion,m25p16", "jedec,spi-nor";
			spi-max-frequency = <40000000>;
			reg = <0>;
			//m25p,fast-read;

			// Values in the partition table should be relative to the
			// flash start address...
			partitions {
				compatible = "fixed-partitions";
				#address-cells = <1>;
				#size-cells = <1>;

				/* FPGA gateware */
				partition@0 {
					label = "gateware";
					reg = <0x0000000 0x80000>;
					read-only;
				};

				/* MiSoC / LiteX BIOS */
				partition@80000 {
					label = "bios";
					reg = <0x00080000 0x8000>;
					read-only;
				};

				/* HDMI2USB Firmware (or Linux Kernel?) */
				partition@88000 {
					label = "firmware";
					reg = <0x00088000 0x178000>;
					read-only;
				};
			};
		};
        };
"""

#	flash@0 {
#		label = "System-firmware";
#
#		/* flash type specific properties */
#	};

"""
		partition@0 {
			label = "bootloader-nor";
			reg = <0 0x40000>;
		};
		partition@0x40000 {
			label = "params-nor";
			reg = <0x40000 0x40000>;
		};
		partition@0x80000 {
			label = "kernel-nor";
			reg = <0x80000 0x200000>;
		};
		partition@0x280000 {
			label = "filesystem-nor";
			reg = <0x240000 0x7d80000>;
		};


flash@0 {
	partitions {
		compatible = "fixed-partitions";
		#address-cells = <1>;
		#size-cells = <1>;

		partition@0 {
			label = "gateware";
			reg = <0x0000000 0x%(gateware_size)x>;
			read-only;
		};

		partition@%(gateware_size)x {
			label = "bios";
			reg = <0x%(gateware_size)x 0x%(bios_size)x>;
			read-only;
		};

		uimage@100000 {
			reg = <0x0100000 0x200000>;
		};
	};
};


"""

templates["gpio"] = """
	gpio1: gpio1 {
		gpio-controller
		 #gpio-cells = <2>;
	};
	gpio2: gpio2 {
		gpio-controller
		 #gpio-cells = <1>;
	};
	[...]

	enable-gpios = <&gpio2 2>;
	data-gpios = <&gpio1 12 0>,
		     <&gpio1 13 0>,
		     <&gpio1 14 0>,
		     <&gpio1 15 0>;

gpio-controller@00000000 {
	compatible = "foo";
	reg = <0x00000000 0x1000>;
	gpio-controller;
	#gpio-cells = <2>;
	ngpios = <18>;
	gpio-line-names = "MMC-CD", "MMC-WP", "VDD eth", "RST eth", "LED R",
		"LED G", "LED B", "Col A", "Col B", "Col C", "Col D",
		"Row A", "Row B", "Row C", "Row D", "NMI button",
		"poweroff", "reset";
}



"""

templates["leds"] = """
leds {
	compatible = "gpio-leds";
	hdd {
		label = "Disk Activity";
		gpios = <&mcu_pio 0 GPIO_ACTIVE_LOW>;
		linux,default-trigger = "disk-activity";
	};

	fault {
		gpios = <&mcu_pio 1 GPIO_ACTIVE_HIGH>;
		/* Keep LED on if BIOS detected hardware fault */
		default-state = "keep";
	};
};


syscon: syscon@10000000 {
	compatible = "syscon", "simple-mfd";
	reg = <0x10000000 0x1000>;

	led@08.0 {
		compatible = "register-bit-led";
		offset = <0x08>;
		mask = <0x01>;
		label = "versatile:0";
		linux,default-trigger = "heartbeat";
		default-state = "on";
	};
	led@08.1 {
		compatible = "register-bit-led";
		offset = <0x08>;
		mask = <0x02>;
		label = "versatile:1";
		linux,default-trigger = "mmc0";
		default-state = "off";
	};
	led@08.2 {
		compatible = "register-bit-led";
		offset = <0x08>;
		mask = <0x04>;
		label = "versatile:2";
		linux,default-trigger = "cpu0";
		default-state = "off";
	};
	led@08.3 {
		compatible = "register-bit-led";
		offset = <0x08>;
		mask = <0x08>;
		label = "versatile:3";
		default-state = "off";
	};
	led@08.4 {
		compatible = "register-bit-led";
		offset = <0x08>;
		mask = <0x10>;
		label = "versatile:4";
		default-state = "off";
	};


"""

templates["gpios"] = """
	gpio-keys {
			compatible = "gpio-keys";
			autorepeat;

			up {
				label = "GPIO Key UP";
				linux,code = <103>;
				gpios = <&gpio1 0 1>;
			};

			down {
				label = "GPIO Key DOWN";
				linux,code = <108>;
				interrupts = <1 IRQ_TYPE_LEVEL_HIGH 7>;
			};
"""

templates["spi2mmc"] = """
	mmc-slot@0 {
		compatible = "fsl,mpc8323rdb-mmc-slot",
			     "mmc-spi-slot";
		reg = <0>;
		gpios = <&qe_pio_d 14 1
			 &qe_pio_d 15 0>;
		voltage-ranges = <3300 3300>;
		spi-max-frequency = <50000000>;
		interrupts = <42>;
		interrupt-parent = <&PIC>;
	};
"""

templates["gpr"] = """
Required properties:
- compatible: Should contain "syscon".
- reg: the register region can be accessed from syscon

Optional property:
- reg-io-width: the size (in bytes) of the IO accesses that should be
  performed on the device.

Examples:
gpr: iomuxc-gpr@020e0000 {
	compatible = "fsl,imx6q-iomuxc-gpr", "syscon";
	reg = <0x020e0000 0x38>;
};
"""

templates["cec"] = """
Common bindings for HDMI CEC adapters

- hdmi-phandle: phandle to the HDMI controller.

- needs-hpd: if present the CEC support is only available when the HPD
  is high. Some boards only let the CEC pin through if the HPD is high,
  for example if there is a level converter that uses the HPD to power
  up or down.
"""

templates["hdmi"] = """
hdmi0: connector@1 {
	compatible = "hdmi-connector";
	label = "hdmi";

	type = "a";

	port {
		hdmi_connector_in: endpoint {
			remote-endpoint = <&tpd12s015_out>;
		};
	};
};
"""


templates["i2c"] = """
i2c@0 {
	compatible = "i2c-gpio";
	gpios = <&pioA 23 0 /* sda */
		 &pioA 24 0 /* scl */
		>;
	i2c-gpio,sda-open-drain;
	i2c-gpio,scl-open-drain;
	i2c-gpio,delay-us = <2>;	/* ~100 kHz */
	#address-cells = <1>;
	#size-cells = <0>;

	rv3029c2@56 {
		compatible = "rv3029c2";
		reg = <0x56>;
	};
};
"""


templates["spiflash4x"] = """
    qspi0: quadspi@40044000 {
            compatible = "fsl,vf610-qspi";
            reg = <0x40044000 0x1000>, <0x20000000 0x10000000>;
            reg-names = "QuadSPI", "QuadSPI-memory";
            interrupts = <0 24 IRQ_TYPE_LEVEL_HIGH>;
            clocks = <&clks VF610_CLK_QSPI0_EN>,
                    <&clks VF610_CLK_QSPI0>;
            clock-names = "qspi_en", "qspi";

            flash0: s25fl128s@0 {
                    ....
            };
    };
"""

templates["eth"] = """
aliases {
	mdio-gpio0 = &mdio0;
};

mdio0: mdio {
	compatible = "virtual,mdio-gpio";
	#address-cells = <1>;
	#size-cells = <0>;
	gpios = <&qe_pio_a 11
		 &qe_pio_c 6>;
};

davinci_mdio: ethernet@0x5c030000 {
	compatible = "ti,davinci_mdio";
	reg = <0x5c030000 0x1000>;
	#address-cells = <1>;
	#size-cells = <0>;

	reset-gpios = <&gpio2 5 GPIO_ACTIVE_LOW>;
	reset-delay-us = <2>;

	ethphy0: ethernet-phy@1 {
		reg = <1>;
	};

	ethphy1: ethernet-phy@3 {
		reg = <3>;
	};
};

ethernet@0 {
	...
	fixed-link {
	      speed = <1000>;
	      full-duplex;
	};
	...
};

ethernet@1 {
	...
	fixed-link {
	      speed = <1000>;
	      pause;
	      link-gpios = <&gpio0 12 GPIO_ACTIVE_HIGH>;
	};
	...
};

/*

local-mac-address:
mac-address:
max-speed:
max-frame-size:
phy-mode: rgmii gmii mii
phy-connection-type:
phy-handle:
phy-device:
managed: 

*/


"""

templates["regmap"] = """
dev: dev@40031000 {
	      compatible = "syscon";
	      reg = <0x40031000 0x1000>;
	      big-endian;
	      ...
};
"""

templates["rst"] = """
	rst: reset-controller {
		#reset-cells = <1>;
	};

	device {
		resets = <&rst 20>;
		reset-names = "reset";
	};

	reboot {
	   compatible = "syscon-reboot";
	   regmap = <&regmapnode>;
	   offset = <0x0>;
	   mask = <0x1>;
	};


"""


_Module = namedtuple("Module", ["name", "location"])
class Module(_Module):
    def __init__(self, *args):
        _Module.__init__(self)
        self.csrs = {}
        self.constants = {}

        self.interrupt = None
        self.ev = None

    def match(self, record_name):
        if record_name.startswith(self.name):
            return record_name[len(self.name)+1:]
        else:
            return False

    @property
    def size(self):
        last_csr = self.location
        for csr in self.csrs.values():
            if csr.location > self.location:
                last_csr = csr.location
        return (last_csr + BUS_DATA_WIDTH) - self.location

    def add_csr(self, csr):
        assert csr.location >= self.location, "CSR location (%s) is less than CSR base!? (%s)" % (
            csr, self)

        self.csrs[csr.name[len(self.name)+1:]] = csr

    def add_constant(self, name, value):
        if name.endswith("interrupt"):
            self.interrupt = value
        else:
            self.constants[name] = value

    def __repr__(self):
        return "%s(name=%r, location=0x%x, csrs=%r)" % (
                self.__class__.__name__, self.name, self.location, tuple(c.name for c in self.csrs.values()))


# FIXME: Is there a way to detect this?
BUS_DATA_WIDTH = 32

class EventManager(Module):
    def __init__(self, name, location):
        Module.__init__(self, name, location)

        assert name.startswith('ev_')

        self.add_csr(CSR("ev_status",  location + 0 * BUS_DATA_WIDTH, 1, "ro"))
        self.add_csr(CSR("ev_pending", location + 1 * BUS_DATA_WIDTH, 1, "rw"))
        self.add_csr(CSR("ev_enable",  location + 2 * BUS_DATA_WIDTH, 1, "rw"))

    def add_csr(self, csr):
        assert csr.name in self.csrs
        assert self.csrs[csr.name[len(self.name)+1:]] == csr


memory_regions = {}
global_constants = {}

modules = {}


def main(argv):
    global modules
    global global_constants
    global memory_regions

    args = parser.parse_args()
    if not args.csr_csv and len(argv) == 2:
        args.csr_csv = sys.argv[1]

    if not args.csr_csv:
        raise SystemError("Provide csr.csv file.")

    def find_module(modules, record_name):
        matches = []
        for modname, module in modules.items():
            if not module.match(record_name):
                continue

            matches.append(module)

        if not matches:
            return None

        matches.sort(key=lambda o: o.name)
        return matches[-1]

    for record_type, record_name, record_value, record_size, record_mode in csv.reader(open(args.csr_csv)):
        if record_type == 'csr_base':
            modules[record_name] = Module(record_name, int(record_value, 16))
        elif record_type == 'csr_register':
            module = find_module(modules, record_name)
            assert module, "Could not find module for CSR %r" % module
            module.add_csr(CSR(record_name, int(record_value, 16), int(record_size), record_mode))
        elif record_type == 'constant':
            try:
                constant_value = int(record_value)
            except ValueError:
                constant_value = record_value

            module = find_module(modules, record_name)
            if module:
                module.add_constant(record_name, constant_value)
            else:
                global_constants[record_name] = constant_value

        elif record_type == 'memory_region':
            memory_regions[record_name] = MemoryRegion(record_name, int(record_value, 16), int(record_size))

    assert 'config_cpu_type' in global_constants
    assert 'config_csr_data_width' in global_constants
    assert global_constants['config_csr_data_width'] == 8

    memories = []
    for memname, memory in memory_regions.items():
        if 'memory-'+memname in templates:
            memories.append(templates['memory-'+memname](memory))
        else:
            memories.append('\t/* No device tree for memory region %s */' % memname)

    devices = []
    for modname, module in sorted(modules.items()):
        if 'device-'+modname in templates:
            devices.append(templates['device-'+modname](module))
        else:
            devices.append('\t/* No device tree for device %s */' % modname)

    dt = templates[global_constants['config_cpu_type'].lower()]({
        'config_clock_frequency': global_constants['config_clock_frequency'],
        'memories': '\n'.join(memories),
        'devices': '\n'.join(devices),
    })
    print(dt)



if __name__ == "__main__":
    import sys
    main(sys.argv)
