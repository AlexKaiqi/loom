# F G3 现有设施裁定

批次[facilities-001](../../../validation/components/f/evidence/facilities-001/result.json)按先行facility-protocol执行，四项原设施预期均获得直接观察。FP01源/恢复13成员一致，FP02rooted archive完整且unrooted对照被GC，FP03旧FD和writable mmap均EAGAIN、新写者SIGIO后阻塞至lease释放，FP04实际目录inode交换且旧FD只写retired对象。

这些不是F组件验收通过。FP01只测试同owner可读数据，未证明任意所有权/不可读文件或恶意归档安全；FP03只测试单regular文件和目录事件，不证明递归监测/溢出/发布窗口；FP04不证明X停止或R数据库事务。源码与协议hash、原始目录/输出在批次中，生产组件仍缺失。

X的storage-preparation-001已直接读取原tar头：checkpoint-1 SHA256 1d1bc33e30f2393c7542e7adf2824cc913329c3bd9e7dbe8b787a0196562a738；checkpoint-2 a68a8f73d7fc1711b0a5d447e1f38ec2ebdb5f04950225f82214f8b2a9f46bc8。8成员保留mode0/软硬链/uidgid/精确PAX时间；user xattr不可用、ACL未测。F host与X导入profile必须分别验收。

选择结论：继续普通目录+GNU pax tar+bare Git rooted refs、Linux read lease/inotify、同文件系统renameat2 exchange。明确失败保留：直接tmpfs docker cp产生空归档；UID1000 exporter漏mode000。它们不能被exit0或新路线成功覆盖。G3只冻结可验证契约，G4仍需正式实现和所有反例。
