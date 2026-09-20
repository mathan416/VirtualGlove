# Power Glove Game ROM Input Audit

This audit is limited to the Power Glove game list shipped in the registry. ROMs
were read from the user's archive folder for static inspection and were not copied
into the repository or release package.

| Game | ROM SHA-256 | Input finding | Shared profile |
| --- | --- | --- | --- |
| Bad Street Brawler (USA) | `be2714f072338f2ca7204be750eaa03daadeb12521e1713cfe54d35b65457700` | Standard NES button polling; in-game Power Glove program choices change how glove motions become those buttons. | `bad_street_brawler` |
| Defender II (USA) | `dbc69122c8d84af7f026e2612cbd0713ce371954e2401610f2acb7aa51dd95e0` | Standard controller polling. | `program_e` |
| Gyruss (USA) | `c6aeb2448aea5c3931e63fb9bafa85300acdbe2c59a9ba500863c2041e0fe9d8` | Standard controller polling. | `program_c` |
| Gun Smoke (USA) | `4ad9629a2bacc158a7f50975869c7dfe533567ae399a5bdc5df2240286df259f` | Standard controller polling. | `program_g` |
| Joust (USA) | `083eb550a39b4821dba154111521cd67826f07769ec0b93db0dd6c5b3fe18837` | Standard controller bits are consumed selectively; no native multi-byte glove packet was found. | `program_b` |
| Knight Rider (USA) | `6e822c93f64347032847bcaa46728eb324e8fe7dc8746a6a9e6512bc7ba39cc2` | Standard controller polling. | `program_i` |
| Sesame Street 123 (USA) | `5d2c0a69e65f1e9c6984025407f5a7198cbf5e1774d2f3a87883327520a91793` | Standard controller polling. | `program_f` |
| Super Glove Ball (USA) | `ad60ef1b62cd1b3bc02a9320376067347a8ab2ebbe46e1616693d8379c9d9a7b` | Detects and consumes a native ten-byte Power Glove stream; also contains a standard-controller fallback. | `super_glove_ball` |

The broad result supports one global camera calibration and recognition model.
FCEUmm receives responsive standard D-pad/button output for seven games and remains
the Super Glove Ball fallback. Only Super Glove Ball benefits from bypassing D-pad
thresholds and sending continuous X/Y through the custom Nestopia core.

Static inspection establishes which controller path the program reads; it does not
replace cabinet play testing. Program labels remain output mappings, not separate
recognition or calibration profiles.
