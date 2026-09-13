# F 返回归档与清单 v1（FR05先行补件）

先行原因：原F驱动只检查Git归档，漏验capture/import_archive交给X的实际archive_path/manifest_path。返回不存在路径或假的成员清单可能通过。旧PASS已撤回并保留；本补件不更改v5性质，不实现F产品。

每个version_ref所指Git commit必须包含archive.tar和manifest.json两个原始blob；archive_sha256、manifest_sha256分别覆盖完整原字节。返回archive_path和manifest_path是control_dir内可实际打开的普通文件，不能是symlink或越出受控根；其字节必须与Git对应blob逐字节一致。允许JSON空白差异，但每个固定版本的实际清单文件字节/hash不得变。路径不是版本授权，resource/domain/profile均与原对象一致。

manifest JSON完整结构为`{schema:"lore-f-manifest/v1",resource_id,domain,profile,tree:{entries,hardlink_groups}}`。entries以可经os.fsencode原样还原的相对路径为key，根为"."；涵盖约定集合的所有实际成员，不能漏ignored/空目录/隐藏.git、不能额外声明不存在成员。每个条目固定kind/mode/mtime_ns/uid/gid/xattrs；数值为JSON整数而非布尔/浮点。file另有size与sha256；symlink另有target_b64；dir无正文。xattrs为属性名→原字节base64。hardlink_groups是树内同inode的路径集合，组内/组间按路径排序，不保存跨恢复无意义的inode编号。

外部observer从真实源/恢复目录的lstat、字节、xattrs、readlink、hardlink关系独立构造期待描述；文件正文只在测试原始观测中保留，manifest只存size/hash，不复制日志或正文成为竞争事实。类型/缺项/多项/内容/模式/范围任一不同失败；重新计算伪造manifest的新hash不能使不存在成员合法。清单缺失/损坏/声明与实际Git归档或返回文件不符时，不能交付X或确认历史读取/恢复。

本轮仅在原F01/F05等19例内补读路径/双blob/hash/完整描述，并增加独立oracle坏包：不存在archive路径、不存在manifest路径、错误manifest hash、重算hash但伪造成员。正式R/X组合仍需原依赖真实验收。
