import sys, configparser, datetime, signal
import encoder, bicoder, decoder, atcoder, alcoder
import tensorflow as tf, numpy as np

def prepad(unpadded, pad, size):
	if len(unpadded) == size:
		return unpadded
	return [pad] * (size - len(unpadded)) + unpadded

def postpad(unpadded, pad, size):
	if len(unpadded) == size:
		return unpadded
	return unpadded + [pad] * (size - len(unpadded))

def feed(model, pretrainer, config, filename):
	batch, length, align = config.getint('global', 'batchsize'), config.getint('global', 'timesize'), config.getboolean('global', 'align')
	inilist, prelist, postlist, alignlist = list(), list(), list(), list()
	for line in open(filename):
		iniedit, preedit, postedit, alignment = line.split('\t')
		lengths = [len(iniedit.split()), len(preedit.split())]
		if align:
			completealign, calign = postpad(alignment.split(';'), '', length), list()
			for i in xrange(length):
				calign.append([prepad(list(), -1., length), prepad(list(), -1., length)])
				if not completealign[i].strip(): continue
				completealign[i] = completealign[i].split(',')
				for ii in xrange(2):
					if not completealign[i][ii].strip(): continue
					indexalign = [int(inalign) for inalign in completealign[i][ii].split(' ') if inalign]
					for idx in indexalign:
						calign[-1][ii][idx + length - lengths[ii]] = 1. / len(indexalign)
			alignlist.append(calign)
		prelist.append(prepad([int(pre) for pre in preedit.split()] + [0], 0, length + 1))
		postlist.append(postpad([int(post) for post in postedit.split()] + [0], 0, length + 1))
		if len(prelist) == batch:
			feeddict = dict()
			feeddict.update({model['exi_%i' %i]: [prelist[ii][i] for ii in xrange(batch)] for i in xrange(length)})
			feeddict.update({model['eyi_%i' %i]: [prelist[ii][i + 1] for ii in xrange(batch)] for i in xrange(length)})
			feeddict.update({model['dyi_%i' %i]: [postlist[ii][i] for ii in xrange(batch)] for i in xrange(length)})
			feeddict.update({pretrainer['exi_%i' %i]: [prelist[ii][i] for ii in xrange(batch)] for i in xrange(length)})
			feeddict.update({pretrainer['eyi_%i' %i]: [prelist[ii][i + 1] for ii in xrange(batch)] for i in xrange(length)})
			if align:
				feeddict.update({model['dai_%i' %i]: [[alignlist[ii][i][1][iii] for ii in xrange(batch)] for iii in xrange(length)] for i in xrange(length)})
			yield feeddict
			inilist, prelist, postlist, alignlist = list(), list(), list(), list()

def run(model, pretrainer, config, session, summary, filename, train):
	iters, freq, time, saves, align, total, totalemss, totaldmss, totaldmsa = config.getint('global', 'iterations') if train else 1, config.getint('global', 'frequency'), config.getint('global', 'timesize'), config.get('global', 'output'), config.getboolean('global', 'align'), 0., 0., 0., 0.
	if config.get('global', 'lfunc') == 'mse': es, te, ses, gse, ds, td, sds, gsd, ps, tp, sps, gsp = model['emse'], model['temse'], model['semse'], model['gse'], model['dmses'], model['tdmses'], model['sdmses'], model['gsd'], pretrainer['emse'], pretrainer['temse'], pretrainer['semse'], pretrainer['gse']
	if config.get('global', 'lfunc') == 'nll': es, te, ses, gse, ds, td, sds, gsd, ps, tp, sps, gsp  = model['enll'], model['tenll'], model['senll'], model['gse'], model['dnlls'], model['tdnlls'], model['sdnlls'], model['gsd'], pretrainer['enll'], pretrainer['tenll'], pretrainer['senll'], pretrainer['gse']
	if config.get('global', 'lfunc') == 'mse' and align: da, sda = model['dmsea'], model['sdmsea']
	if config.get('global', 'lfunc') == 'nll' and align: da, sda = model['dmsea'], model['sdmsea']

	for i in xrange(iters):
		for ii, feeddict in enumerate(feed(model, pretrainer, config, filename)):
			if train == 'pretrain2':
				valemss, t = session.run([es, te], feed_dict = feeddict)
				totalemss += valemss
				if (ii + 1) % freq == 0:
					summs = session.run(ses, feed_dict = feeddict)
					summary.add_summary(summs, gse.eval())
					print datetime.datetime.now(), 'iteration', i, 'batch', ii, 'loss:', 'seq', valemss, totalemss
			if train == 'pretrain3':
				valemss, t = session.run([ps, tp], feed_dict = feeddict)
				totalemss += valemss
				if (ii + 1) % freq == 0:
					summs = session.run(sps, feed_dict = feeddict)
					summary.add_summary(summs, gsp.eval())
					print datetime.datetime.now(), 'iteration', i, 'batch', ii, 'loss:', 'seq', valemss, totalemss
			elif train == 'train':
				if align:
					valdmss, valdmsa, t = session.run([ds, da, td], feed_dict = feeddict)
					totaldmss += valdmss
					totaldmsa += valdmsa
					if (ii + 1) % freq == 0:
						summs, summa = session.run([sds, sda], feed_dict = feeddict)
						summary.add_summary(summs, gsd.eval())
						summary.add_summary(summa, gsd.eval())
						print datetime.datetime.now(), 'iteration', i, 'batch', ii, 'loss:', 'seq', valdmss, totaldmss, 'att', valdmsa, totaldmsa
				else:
					val, t = session.run([ds, td], feed_dict = feeddict)
					total += val
					if (ii + 1) % freq == 0:
						summ = session.run(sds, feed_dict = feeddict)
						summary.add_summary(summ, gsd.eval())
						print datetime.datetime.now(), 'iteration', i, 'batch', ii, 'loss', val, total
			elif train == 'dev' or train == 'test':
				val = session.run([model['dp_%i' %iii] for iii in xrange(time)], feed_dict = feeddict)
				exps, vals, outs = [feeddict[model['dyi_%i' %iii]] for iii in xrange(time)], [x[0] for x in val], [x[1] for x in val]
				np.savez(open('%s/%i' %(saves, ii), 'w'), values = np.transpose(np.array(vals), [1, 0, 2]), outputs = np.transpose(np.array(outs), [1, 0, 2]))
				for bexp, bout in zip(exps, outs):
					for exp, out in zip(bexp, bout):
						if exp == 0: continue
						if exp in out: total += 1

	if train == 'pretrain': return totalemss
	elif train == 'train' and align: return totaldmss, totaldmsa
	else: return total

def handler(signum, stack):
	print datetime.datetime.now(), 'terminating execution'
	print datetime.datetime.now(), 'saving model'
	tf.train.Saver().save(sess, config.get('global', 'save'))
	sys.exit()

if __name__ == '__main__':
	config = configparser.ConfigParser(interpolation = configparser.ExtendedInterpolation())
	config.read(sys.argv[1])
	signal.signal(signal.SIGINT, handler)

	print datetime.datetime.now(), 'creating model'
	embedding, model, mode = np.loadtxt('%s/model' %config.get('global', 'data')).astype(np.float32), dict(), [int(sys.argv[2]) % 2, (int(sys.argv[2]) / 2) % 3]
	if mode[0] == 0: model = encoder.create(model, config['encoder'], embedding)
	if mode[0] == 1: model = bicoder.create(model, config['bicoder'], embedding)
	if mode[1] == 0: model = decoder.create(model, config['decoder'])
	if mode[1] == 1: model = atcoder.create(model, config['atcoder'])
	if mode[1] == 2: model = alcoder.create(model, config['alcoder'])
	pretrainer = encoder.create(dict(), config['encoder'], embedding)

	with tf.Session() as sess:
		if sys.argv[3] == 'init':
			sess.run(tf.initialize_all_variables())
		else:
			tf.train.Saver().restore(sess, config.get('global', 'load'))
			if sys.argv[3] == 'retrain': sys.argv[3] = 'train'
			elif sys.argv[3] == 'train': sess.run([model['dW%s_%i' %(descriptor, depth)].assign(pretrainer['eW%s_%i' %(descriptor, depth)]) for depth in xrange(config.getint('global', 'depth')) for descriptor in ['i', 'f', 'o', 'c', 'z']])
			summary = tf.train.SummaryWriter(config.get('global', 'logs'), sess.graph)
			print datetime.datetime.now(), 'running model'
			returnvalue = run(model, pretrainer, config, sess, summary, '%s/%s' %(config.get('global', 'data'), sys.argv[3]), sys.argv[3])
			print datetime.datetime.now(), 'returned value', returnvalue
		print datetime.datetime.now(), 'saving model'
		tf.train.Saver().save(sess, config.get('global', 'save'))
